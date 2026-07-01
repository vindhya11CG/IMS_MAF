"""Supplier Selection Agent - Phase 5 of Inventory Management System."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from agents.replenishment_planning.models import ReplenishmentOrder
from utils.csv_loader import CsvInventoryDataLoader
from config import AzureOpenAIClient
from .models import SupplierSelectionResult, SupplierSelectionSummary
from .services import PolicyEvaluationService, SupplierEvaluationService

logger = logging.getLogger(__name__)


class SupplierSelectionAgent:
    """
    Supplier Selection Agent - Phase 5.
    
    Consumes ReplenishmentOrder objects from Phase 4 (Replenishment Planning)
    and generates final supplier selections based on:
    - Policy compliance (cost variance, reliability, lead times)
    - Supplier performance scores
    - Risk assessment
    - Multi-supplier options (for dual sourcing)
    - Budget constraints
    """

    def __init__(
        self,
        loader: Optional[CsvInventoryDataLoader] = None,
        policy_evaluation_service: Optional[PolicyEvaluationService] = None,
        supplier_evaluation_service: Optional[SupplierEvaluationService] = None,
        openai_client: Optional[AzureOpenAIClient] = None,
        policy_name: str = "STANDARD",
    ) -> None:
        self.loader = loader or CsvInventoryDataLoader()
        self.policy_evaluation_service = (
            policy_evaluation_service or PolicyEvaluationService()
        )
        self.supplier_evaluation_service = (
            supplier_evaluation_service or SupplierEvaluationService(self.loader)
        )
        self.openai_client = openai_client
        self.policy_name = policy_name
        self.policy = self.policy_evaluation_service.get_policy(policy_name)

        # Cache product and supplier lookup data once to avoid repeated file read overhead.
        self.product_category_map = self._load_product_category_map()
        self.supplier_category_mappings = self.loader.load_supplier_category_mapping()
        self.pricing_tiers = self.loader.load_supplier_pricing_tiers()
        self.suppliers_by_id = {
            supplier.get("supplier_id"): supplier
            for supplier in self.loader.load_suppliers()
            if supplier.get("supplier_id") is not None
        }

        logger.info(f"SupplierSelectionAgent initialized with policy: {policy_name}")

    def execute(self, replenishment_orders: List[ReplenishmentOrder]) -> dict[str, object]:
        """
        Execute supplier selection workflow.
        
        Args:
            replenishment_orders: List of ReplenishmentOrder objects from Phase 4
            
        Returns:
            Dictionary with selections, summary, and optional Azure analysis
        """
        try:
            logger.info("="*80)
            logger.info("SUPPLIER SELECTION AGENT - STARTING WORKFLOW")
            logger.info("="*80)
            
            if not replenishment_orders:
                logger.info("No replenishment orders to process.")
                return self._build_empty_result()
            
            logger.info(f"\n[PHASE 5.1] Processing {len(replenishment_orders)} replenishment orders...")
            
            # Evaluate suppliers for each order
            logger.info("\n[PHASE 5.2] Evaluating suppliers against policies...")
            selections = self._evaluate_and_select_suppliers(replenishment_orders)
            logger.info(f"  Selected suppliers for {len(selections)} orders")
            
            # Generate summary
            summary = self._generate_summary(selections, replenishment_orders)
            azure_analysis = None
            
            if self.openai_client is not None:
                logger.info("\n[AZURE ANALYSIS] Sending supplier selections to Azure OpenAI...")
                messages = [
                    self.openai_client.build_system_message(),
                    {
                        "role": "user",
                        "content": self._build_openai_prompt(selections),
                    },
                ]
                azure_analysis = self.openai_client.create_chat_completion(messages)
                logger.info("  Analysis complete")
            
            logger.info("\n" + "="*80)
            logger.info("SUPPLIER SELECTION AGENT - WORKFLOW COMPLETE")
            logger.info("="*80)
            
            return {
                "orders_processed": len(replenishment_orders),
                "selections": selections,
                "summary": summary,
                "azure_analysis": azure_analysis,
            }
        except Exception as e:
            logger.error(f"Error in supplier selection workflow: {e}", exc_info=True)
            raise

    def _evaluate_and_select_suppliers(
        self,
        replenishment_orders: List[ReplenishmentOrder],
    ) -> List[SupplierSelectionResult]:
        """Evaluate and select suppliers for all replenishment orders."""
        selections = []
        
        for order in replenishment_orders:
            # Get all possible suppliers for this SKU from DB4
            all_suppliers = self._get_suppliers_for_sku(order.sku_id)
            
            if not all_suppliers:
                logger.warning(f"No suppliers found for SKU {order.sku_id}, using original supplier")
                # Use the supplier from the original replenishment order
                selection = SupplierSelectionResult(
                    order_id=order.order_id,
                    sku_id=order.sku_id,
                    location_id=order.location_id,
                    selected_supplier_id=order.supplier_id,
                    selected_supplier_name=order.supplier_name,
                    order_quantity=order.order_quantity,
                    unit_cost=order.unit_cost,
                    total_cost=order.total_cost,
                    lead_time_days=order.lead_time_days,
                    selection_rationale="No alternatives found, using original supplier selection",
                    policy_compliant=True,
                    approval_required=False,
                )
                selections.append(selection)
                continue
            
            # Prepare cost data for evaluation
            costs_by_supplier = {}
            for supplier_id in all_suppliers:
                unit_cost = self._get_supplier_unit_cost(supplier_id, order.sku_id, order.order_quantity)
                if unit_cost is not None:
                    total_cost = unit_cost * order.order_quantity
                    lead_time = self._get_supplier_lead_time(supplier_id)
                    costs_by_supplier[supplier_id] = (unit_cost, total_cost, lead_time)
            
            if not costs_by_supplier:
                logger.warning(f"No pricing data for SKU {order.sku_id}")
                continue
            
            # Evaluate suppliers
            evaluations = self.supplier_evaluation_service.execute(
                supplier_ids=list(costs_by_supplier.keys()),
                order_id=order.order_id,
                sku_id=order.sku_id,
                location_id=order.location_id,
                costs_by_supplier=costs_by_supplier,
            )
            
            # Apply policy to each evaluation
            lowest_cost = min(cost[0] for cost in costs_by_supplier.values())
            policy_compliant_options = []
            exceptions = []
            
            for evaluation in evaluations:
                evaluation = self.policy_evaluation_service.execute(
                    evaluation,
                    policy_name=self.policy_name,
                    lowest_cost=lowest_cost,
                )
                
                if evaluation.policy_compliance:
                    policy_compliant_options.append(evaluation)
                else:
                    exceptions.append(evaluation)
            
            # Select best option (prefer policy-compliant)
            if policy_compliant_options:
                best_eval = policy_compliant_options[0]
                approval_required = False
                rationale = f"Selected {best_eval.supplier_name} - policy compliant, best performance score ({best_eval.final_score:.1f})"
            else:
                # All options violate policy, select best anyway but flag for approval
                best_eval = evaluations[0]
                approval_required = True
                rationale = f"Selected {best_eval.supplier_name} - policy exceptions: {', '.join(best_eval.compliance_issues)}. Requires approval."
                logger.warning(f"Order {order.order_id}: All suppliers violate policy, flagging for approval")
            
            selection = SupplierSelectionResult(
                order_id=order.order_id,
                sku_id=order.sku_id,
                location_id=order.location_id,
                selected_supplier_id=best_eval.supplier_id,
                selected_supplier_name=best_eval.supplier_name,
                order_quantity=order.order_quantity,
                unit_cost=best_eval.unit_cost,
                total_cost=best_eval.total_cost,
                lead_time_days=best_eval.lead_time_days,
                selection_rationale=rationale,
                policy_compliant=best_eval.policy_compliance,
                backup_supplier_id=policy_compliant_options[1].supplier_id if len(policy_compliant_options) > 1 else None,
                backup_supplier_name=policy_compliant_options[1].supplier_name if len(policy_compliant_options) > 1 else None,
                approval_required=approval_required,
            )
            
            selections.append(selection)
        
        return selections

    def _load_product_category_map(self) -> dict[int, int]:
        """Load SKU -> category mapping once."""
        try:
            products = self.loader.load_products()
            return {
                product.get("sku_id"): product.get("category_id")
                for product in products
                if product.get("sku_id") is not None
            }
        except Exception as e:
            logger.error(f"Error loading product category map: {e}")
            return {}

    def _get_sku_category_id(self, sku_id: int) -> Optional[int]:
        """Get the product category for a given SKU."""
        return self.product_category_map.get(sku_id)

    def _get_suppliers_for_sku(self, sku_id: int) -> List[int]:
        """Get all supplier IDs that supply a specific SKU."""
        category_id = self._get_sku_category_id(sku_id)
        if category_id is None:
            return []

        supplier_ids = [
            mapping["supplier_id"]
            for mapping in self.supplier_category_mappings
            if mapping.get("category_id") == category_id
        ]
        return list(set(supplier_ids))

    def _get_supplier_unit_cost(self, supplier_id: int, sku_id: int, order_qty: int) -> Optional[float]:
        """Get unit cost for supplier-SKU with volume-based pricing."""
        category_id = self._get_sku_category_id(sku_id)
        if category_id is None:
            return None

        mappings = [
            m for m in self.supplier_category_mappings
            if m.get("supplier_id") == supplier_id and m.get("category_id") == category_id
        ]
        if not mappings:
            return None

        base_cost = float(mappings[0].get("unit_cost", 0) or 0)
        if base_cost <= 0:
            return None

        matching_tiers = [
            t for t in self.pricing_tiers
            if t.get("supplier_id") == supplier_id
            and t.get("category_id") == category_id
            and t.get("min_qty", 0) <= order_qty
            and (t.get("max_qty", float("inf")) >= order_qty or t.get("max_qty") == 0)
        ]

        if matching_tiers:
            best_tier = max(matching_tiers, key=lambda t: t.get("min_qty", 0))
            discount_percent = float(best_tier.get("discount_percent", 0) or 0)
            return max(0.0, base_cost * (1.0 - discount_percent / 100.0))

        return base_cost

    def _get_supplier_lead_time(self, supplier_id: int) -> int:
        """Get lead time in days for a supplier."""
        supplier = self.suppliers_by_id.get(supplier_id)
        if supplier:
            try:
                return int(supplier.get("lead_time_days", 7))
            except (TypeError, ValueError):
                return 7
        return 7  # Default

    def _generate_summary(
        self,
        selections: List[SupplierSelectionResult],
        original_orders: List[ReplenishmentOrder],
    ) -> SupplierSelectionSummary:
        """Generate summary of supplier selection results."""
        
        total_cost = sum(s.total_cost for s in selections)
        original_cost = sum(o.total_cost for o in original_orders)
        cost_savings = original_cost - total_cost
        
        policy_compliant = sum(1 for s in selections if s.policy_compliant)
        approval_required = sum(1 for s in selections if s.approval_required)
        
        unique_suppliers = len(set(s.selected_supplier_id for s in selections))
        avg_lead_time = (
            sum(s.lead_time_days for s in selections) / len(selections)
            if selections else 0
        )
        
        exceptions = [
            {
                "order_id": s.order_id,
                "sku_id": s.sku_id,
                "reason": s.selection_rationale,
                "approval_required": s.approval_required,
            }
            for s in selections if s.approval_required
        ]
        
        return SupplierSelectionSummary(
            total_orders_evaluated=len(original_orders),
            total_orders_selected=len(selections),
            total_procurement_cost=total_cost,
            policy_compliant_orders=policy_compliant,
            orders_requiring_approval=approval_required,
            average_lead_time=avg_lead_time,
            supplier_diversity=unique_suppliers,
            cost_savings_vs_initial=cost_savings,
            selections=selections,
            exceptions=exceptions,
        )

    def _build_openai_prompt(self, selections: List[SupplierSelectionResult]) -> str:
        """Build prompt for Azure OpenAI analysis."""
        top_selections = sorted(
            selections,
            key=lambda s: s.total_cost,
            reverse=True,
        )[:10]
        
        approval_needed = [s for s in selections if s.approval_required]
        
        prompt_lines = [
            "Review the following supplier selections and provide recommendations.",
            "Consider cost optimization, risk mitigation, and policy compliance.",
            "",
        ]
        
        if approval_needed:
            prompt_lines.extend([
                f"POLICY EXCEPTIONS ({len(approval_needed)} orders require approval):",
            ])
            for selection in approval_needed[:5]:
                prompt_lines.append(
                    f"  • Order {selection.order_id}: {selection.selection_rationale}"
                )
            if len(approval_needed) > 5:
                prompt_lines.append(f"  • ... and {len(approval_needed) - 5} more")
            prompt_lines.append("")
        
        prompt_lines.extend([
            "Top 10 highest-cost selections:",
        ])
        
        for selection in top_selections:
            prompt_lines.append(
                f"  • Order {selection.order_id}: {selection.selected_supplier_name}, "
                f"qty={selection.order_quantity}, cost=${selection.total_cost:.2f}, "
                f"lead_time={selection.lead_time_days}d, "
                f"policy_compliant={'Yes' if selection.policy_compliant else 'No (REQUIRES APPROVAL)'}"
            )
        
        return "\n".join(prompt_lines)

    def _build_empty_result(self) -> dict[str, object]:
        """Build result when no orders provided."""
        return {
            "orders_processed": 0,
            "selections": [],
            "summary": SupplierSelectionSummary(
                total_orders_evaluated=0,
                total_orders_selected=0,
                total_procurement_cost=0.0,
                policy_compliant_orders=0,
                orders_requiring_approval=0,
                average_lead_time=0.0,
                supplier_diversity=0,
                cost_savings_vs_initial=0.0,
                selections=[],
                exceptions=[],
            ),
            "azure_analysis": None,
        }
