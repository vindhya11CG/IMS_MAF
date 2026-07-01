"""Replenishment Planning Agent - Phase 4 of Inventory Management System."""

from __future__ import annotations

import logging
from typing import List, Optional

from agents.inventory_monitoring.models import RiskAssessment
from utils.csv_loader import CsvInventoryDataLoader
from config import AzureOpenAIClient
from .models import ReplenishmentOrder, ReplenishmentPlanSummary, SupplierInfo
from .services import OrderCalculationService, SupplierMatchingService

logger = logging.getLogger(__name__)


class ReplenishmentPlanningAgent:
    """
    Replenishment Planning Agent - Phase 4.
    
    Consumes RiskAssessment objects from Phase 3 (Inventory Risk Monitoring)
    and generates replenishment orders based on:
    - Risk conditions (stock levels vs reorder points)
    - Economic Order Quantity (EOQ) calculations
    - Supplier selection and pricing
    - Lead times and reliability
    """

    def __init__(
        self,
        loader: Optional[CsvInventoryDataLoader] = None,
        supplier_matching_service: Optional[SupplierMatchingService] = None,
        order_calculation_service: Optional[OrderCalculationService] = None,
        openai_client: Optional[AzureOpenAIClient] = None,
    ) -> None:
        self.loader = loader or CsvInventoryDataLoader()
        self.supplier_matching_service = (
            supplier_matching_service or SupplierMatchingService(self.loader)
        )
        self.order_calculation_service = (
            order_calculation_service or OrderCalculationService()
        )
        self.openai_client = openai_client
        logger.info("ReplenishmentPlanningAgent initialized")

    def execute(self, risk_assessments: List[RiskAssessment]) -> dict[str, object]:
        """
        Execute replenishment planning workflow.
        
        Args:
            risk_assessments: List of RiskAssessment objects from Phase 3
            
        Returns:
            Dictionary with orders, summary, and optional Azure analysis
        """
        try:
            logger.info("="*80)
            logger.info("REPLENISHMENT PLANNING AGENT - STARTING WORKFLOW")
            logger.info("="*80)
            
            # Filter risky items
            risky_items = [a for a in risk_assessments if a.risk_detected]
            logger.info(f"\n[PHASE 4.1] Filtered {len(risky_items)} risky items from {len(risk_assessments)} assessments")
            
            if not risky_items:
                logger.info("No risky items detected. No replenishment orders needed.")
                return self._build_empty_result()
            
            # Match suppliers for risky items
            logger.info("\n[PHASE 4.2] Matching suppliers for risky items...")
            suppliers: dict[int, SupplierInfo] = {}
            for assessment in risky_items:
                supplier = self.supplier_matching_service.execute(
                    assessment.sku_id,
                    order_qty=1,
                )
                if supplier:
                    suppliers[assessment.sku_id] = supplier
            
            logger.info(f"  Matched suppliers for {len(suppliers)} unique SKUs")
            
            # Generate orders
            logger.info("\n[PHASE 4.3] Generating replenishment orders...")
            orders = self.order_calculation_service.execute(risky_items, suppliers)
            logger.info(f"  Generated {len(orders)} orders")
            
            # Generate summary
            summary = self._generate_summary(orders, risky_items)
            azure_analysis = None
            
            if self.openai_client is not None:
                logger.info("\n[AZURE ANALYSIS] Sending replenishment orders to Azure OpenAI...")
                messages = [
                    self.openai_client.build_system_message(),
                    {
                        "role": "user",
                        "content": self._build_openai_prompt(orders),
                    },
                ]
                azure_analysis = self.openai_client.create_chat_completion(messages)
                logger.info("  Analysis complete")
            
            logger.info("\n" + "="*80)
            logger.info("REPLENISHMENT PLANNING AGENT - WORKFLOW COMPLETE")
            logger.info("="*80)
            
            return {
                "risk_assessments_input": len(risk_assessments),
                "risky_items_processed": len(risky_items),
                "orders": orders,
                "summary": summary,
                "azure_analysis": azure_analysis,
            }
        except Exception as e:
            logger.error(f"Error in replenishment planning workflow: {e}", exc_info=True)
            raise

    def _generate_summary(
        self,
        orders: List[ReplenishmentOrder],
        risky_items: List[RiskAssessment],
    ) -> ReplenishmentPlanSummary:
        """Generate summary of replenishment planning results."""
        
        priority_counts = {"URGENT": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        total_cost = 0.0
        total_lead_time = 0
        
        for order in orders:
            priority_counts[order.order_priority] += 1
            total_cost += order.total_cost
            total_lead_time += order.lead_time_days
        
        avg_lead_time = (
            total_lead_time / len(orders) if orders else 0
        )
        
        return ReplenishmentPlanSummary(
            total_orders_generated=len(orders),
            total_order_cost=total_cost,
            orders_by_priority=priority_counts,
            average_lead_time=avg_lead_time,
            risky_items_processed=len(risky_items),
            orders=orders,
        )

    def _build_openai_prompt(self, orders: List[ReplenishmentOrder]) -> str:
        """Build prompt for Azure OpenAI analysis."""
        top_orders = sorted(
            orders,
            key=lambda o: (
                {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(o.order_priority, 999),
                -o.total_cost,
            ),
        )[:10]
        
        prompt_lines = [
            "Review the following replenishment orders and provide recommendations.",
            "Consider order urgency, costs, lead times, and supplier reliability.",
            "Suggest optimization strategies for procurement and inventory management.",
            "",
            "Top replenishment orders:",
        ]
        
        for order in top_orders:
            prompt_lines.append(
                f"Order {order.order_id}: SKU {order.sku_id} @ Location {order.location_id}, "
                f"qty={order.order_quantity}, priority={order.order_priority}, "
                f"supplier={order.supplier_name}, lead_time={order.lead_time_days}d, "
                f"cost=${order.total_cost:.2f}"
            )
        
        return "\n".join(prompt_lines)

    def _build_empty_result(self) -> dict[str, object]:
        """Build result when no risky items found."""
        return {
            "risk_assessments_input": 0,
            "risky_items_processed": 0,
            "orders": [],
            "summary": ReplenishmentPlanSummary(
                total_orders_generated=0,
                total_order_cost=0.0,
                orders_by_priority={"URGENT": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
                average_lead_time=0.0,
                risky_items_processed=0,
                orders=[],
            ),
            "azure_analysis": None,
        }
