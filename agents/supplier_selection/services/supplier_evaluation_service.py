"""Supplier evaluation and performance scoring service."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from utils.csv_loader import CsvInventoryDataLoader
from .base_service import SupplierSelectionService
from ..models import SupplierEvaluation, SupplierPerformanceScore

logger = logging.getLogger(__name__)


class SupplierEvaluationService(SupplierSelectionService):
    """Evaluates suppliers and generates performance scores."""

    def __init__(self, loader: Optional[CsvInventoryDataLoader] = None) -> None:
        super().__init__(name="SupplierEvaluationService")
        self.loader = loader or CsvInventoryDataLoader()
        self.suppliers: Dict[int, Dict] = {}
        self.performance_metrics: Dict[int, Dict] = {}
        self.risk_profiles: Dict[int, Dict] = {}
        self._load_supplier_data()

    def _load_supplier_data(self) -> None:
        """Load all supplier-related data from DB4."""
        try:
            # Load suppliers
            suppliers = self.loader.load_suppliers()
            for supplier in suppliers:
                sid = supplier.get("supplier_id")
                if sid:
                    self.suppliers[sid] = supplier
            logger.info(f"Loaded {len(self.suppliers)} suppliers")

            # Load performance metrics
            metrics = self.loader.load_supplier_performance_metrics()
            for metric in metrics:
                sid = metric.get("supplier_id")
                if sid:
                    self.performance_metrics[sid] = metric
            logger.info(f"Loaded performance metrics for {len(self.performance_metrics)} suppliers")

            # Load risk profiles
            try:
                profiles = self.loader.load_supplier_risk_profile()
                for profile in profiles:
                    sid = profile.get("supplier_id")
                    if sid:
                        self.risk_profiles[sid] = profile
                logger.info(f"Loaded risk profiles for {len(self.risk_profiles)} suppliers")
            except Exception as e:
                logger.warning(f"Could not load supplier risk profiles: {e}")
        except Exception as e:
            logger.error(f"Error loading supplier data: {e}")

    def calculate_performance_score(self, supplier_id: int) -> SupplierPerformanceScore:
        """Calculate composite performance score for a supplier."""
        supplier = self.suppliers.get(supplier_id, {})
        metrics = self.performance_metrics.get(supplier_id, {})
        risk_profile = self.risk_profiles.get(supplier_id, {})

        on_time = float(metrics.get("on_time_delivery_rate", 0.8))
        quality = float(metrics.get("quality_score", 0.8))
        defect_rate = float(metrics.get("defect_rate", 0.05))
        financial_stability = float(risk_profile.get("financial_stability_score", 0.8))

        # Composite score: weighted average of key metrics
        # Higher is better, scale 0-100
        overall_score = (
            (on_time * 100 * 0.35) +  # On-time delivery weight
            (quality * 100 * 0.30) +  # Quality weight
            ((1.0 - defect_rate) * 100 * 0.20) +  # Defect rate (inverted)
            (financial_stability * 100 * 0.15)  # Financial stability
        )

        compliance_status = risk_profile.get("regulatory_compliance_status", "COMPLIANT")

        return SupplierPerformanceScore(
            supplier_id=supplier_id,
            supplier_name=supplier.get("supplier_name", "Unknown"),
            on_time_delivery_rate=on_time,
            quality_score=quality,
            defect_rate=defect_rate,
            financial_stability_score=financial_stability,
            compliance_status=compliance_status,
            overall_score=min(100, overall_score),  # Cap at 100
        )

    def calculate_risk_score(self, supplier_id: int) -> float:
        """
        Calculate risk score for a supplier (0-100, lower is better).
        
        Considers:
        - Performance metrics
        - Financial stability
        - Compliance status
        - Geographic risk
        """
        performance = self.calculate_performance_score(supplier_id)
        risk_profile = self.risk_profiles.get(supplier_id, {})

        # Base risk (inverse of performance)
        performance_risk = 100 - performance.overall_score

        # Financial stability risk
        financial_risk = (1 - performance.financial_stability_score) * 20

        # Compliance risk
        compliance_status = performance.compliance_status
        compliance_risk = 0
        if compliance_status == "NON_COMPLIANT":
            compliance_risk = 30
        elif compliance_status == "AT_RISK":
            compliance_risk = 15

        # Geographic risk
        geographic_risk = 0
        geo_risk_level = risk_profile.get("geographic_risk", "LOW")
        if geo_risk_level == "HIGH":
            geographic_risk = 15
        elif geo_risk_level == "MEDIUM":
            geographic_risk = 8

        # Composite risk score
        total_risk = (
            (performance_risk * 0.40) +
            (financial_risk * 0.20) +
            (compliance_risk * 0.25) +
            (geographic_risk * 0.15)
        )

        return min(100, total_risk)  # Cap at 100

    def evaluate_for_order(
        self,
        supplier_id: int,
        order_id: str,
        sku_id: int,
        location_id: int,
        unit_cost: float,
        total_cost: float,
        lead_time_days: int,
    ) -> SupplierEvaluation:
        """Create supplier evaluation for a specific order."""
        supplier = self.suppliers.get(supplier_id, {})
        performance = self.calculate_performance_score(supplier_id)
        risk_score = self.calculate_risk_score(supplier_id)

        # Calculate final score (0-100, higher is better)
        # Composite: high performance + low risk = high score
        final_score = (performance.overall_score * 0.7) + ((100 - risk_score) * 0.3)

        return SupplierEvaluation(
            supplier_id=supplier_id,
            supplier_name=supplier.get("supplier_name", "Unknown"),
            order_id=order_id,
            sku_id=sku_id,
            location_id=location_id,
            unit_cost=unit_cost,
            total_cost=total_cost,
            lead_time_days=lead_time_days,
            reliability_score=performance.on_time_delivery_rate,
            policy_compliance=True,  # Will be updated by policy service
            compliance_issues=[],
            risk_score=risk_score,
            final_score=final_score,
        )

    def execute(
        self,
        supplier_ids: List[int],
        order_id: str,
        sku_id: int,
        location_id: int,
        costs_by_supplier: Dict[int, tuple],  # supplier_id -> (unit_cost, total_cost, lead_time)
    ) -> List[SupplierEvaluation]:
        """
        Evaluate multiple suppliers for an order.
        
        Args:
            supplier_ids: List of supplier IDs to evaluate
            order_id: Order ID being evaluated
            sku_id: SKU ID
            location_id: Location ID
            costs_by_supplier: Dict mapping supplier_id to (unit_cost, total_cost, lead_time_days)
            
        Returns:
            List of SupplierEvaluation objects, sorted by final_score (best first)
        """
        evaluations = []

        for supplier_id in supplier_ids:
            if supplier_id not in costs_by_supplier:
                logger.warning(f"No cost data for supplier {supplier_id}")
                continue

            unit_cost, total_cost, lead_time = costs_by_supplier[supplier_id]
            
            evaluation = self.evaluate_for_order(
                supplier_id=supplier_id,
                order_id=order_id,
                sku_id=sku_id,
                location_id=location_id,
                unit_cost=unit_cost,
                total_cost=total_cost,
                lead_time_days=lead_time,
            )
            evaluations.append(evaluation)

        # Sort by final score (highest first = best)
        evaluations.sort(key=lambda e: e.final_score, reverse=True)
        logger.info(f"Evaluated {len(evaluations)} suppliers for order {order_id}")

        return evaluations
