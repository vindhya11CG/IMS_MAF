"""Supplier matching service for replenishment planning."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from utils.csv_loader import CsvInventoryDataLoader
from .base_service import ReplenishmentService
from ..models import SupplierInfo

logger = logging.getLogger(__name__)


class SupplierMatchingService(ReplenishmentService):
    """Matches SKUs with best suppliers from DB4 using pricing tiers and performance metrics."""

    def __init__(self, loader: Optional[CsvInventoryDataLoader] = None) -> None:
        super().__init__(name="SupplierMatchingService")
        self.loader = loader or CsvInventoryDataLoader()
        self.suppliers: Dict[int, Dict] = {}  # supplier_id -> supplier data
        self.pricing_tiers: List[Dict] = []
        self.performance_metrics: Dict[int, Dict] = {}  # supplier_id -> metrics
        self._load_all_data()

    def _load_all_data(self) -> None:
        """Load supplier data, pricing, and performance metrics from DB4."""
        try:
            # Load suppliers
            suppliers = self.loader.load_suppliers()
            for supplier in suppliers:
                sid = supplier.get("supplier_id")
                if sid:
                    self.suppliers[sid] = supplier
            logger.info(f"Loaded {len(self.suppliers)} suppliers")
            
            # Load pricing tiers
            self.pricing_tiers = self.loader.load_supplier_pricing_tiers()
            logger.info(f"Loaded {len(self.pricing_tiers)} pricing tiers")
            
            # Load performance metrics
            metrics = self.loader.load_supplier_performance_metrics()
            for metric in metrics:
                sid = metric.get("supplier_id")
                if sid:
                    self.performance_metrics[sid] = metric
            logger.info(f"Loaded performance metrics for {len(self.performance_metrics)} suppliers")
        except Exception as e:
            logger.error(f"Error loading supplier data: {e}")

    def _get_unit_cost(self, supplier_id: int, sku_id: int, order_qty: int) -> float:
        """Get unit cost for a supplier-SKU pair based on order quantity (pricing tiers)."""
        matching_tiers = [
            t for t in self.pricing_tiers
            if t.get("supplier_id") == supplier_id
            and t.get("sku_id") == sku_id
            and t.get("min_qty", 0) <= order_qty
            and (t.get("max_qty", float("inf")) >= order_qty or t.get("max_qty") == 0)
        ]
        
        if matching_tiers:
            # Return price from best matching tier (closest min_qty)
            best_tier = max(matching_tiers, key=lambda t: t.get("min_qty", 0))
            return float(best_tier.get("unit_price", 0))
        
        # Fallback to default pricing tier if no exact match
        default_tiers = [
            t for t in self.pricing_tiers
            if t.get("supplier_id") == supplier_id and t.get("sku_id") == sku_id
        ]
        if default_tiers:
            return float(default_tiers[0].get("unit_price", 0))
        
        return 0.0

    def _get_reliability_score(self, supplier_id: int) -> float:
        """Calculate reliability score based on performance metrics."""
        metrics = self.performance_metrics.get(supplier_id, {})
        
        on_time = float(metrics.get("on_time_delivery_rate", 0.8))
        quality = float(metrics.get("quality_score", 0.8))
        
        return (on_time * 0.6) + (quality * 0.4)

    def execute(self, sku_id: int, order_qty: int = 100) -> Optional[SupplierInfo]:
        """
        Get the best supplier for a SKU-Order pair.
        
        Considers:
        - Unit cost (with pricing tier discounts)
        - Lead time
        - Reliability score
        - Minimum order requirements
        
        Args:
            sku_id: SKU to find supplier for
            order_qty: Proposed order quantity (used for tier pricing)
            
        Returns:
            Best SupplierInfo or None if no supplier found
        """
        # Find all suppliers that offer this SKU
        candidates = [
            (sid, s) for sid, s in self.suppliers.items()
            if any(t.get("sku_id") == sku_id for t in self.pricing_tiers if t.get("supplier_id") == sid)
        ]
        
        if not candidates:
            logger.warning(f"No suppliers found for SKU {sku_id}")
            return None

        # Score each supplier
        scored_candidates = []
        for supplier_id, supplier in candidates:
            unit_cost = self._get_unit_cost(supplier_id, sku_id, order_qty)
            
            if unit_cost <= 0:
                continue  # Skip if no valid pricing
            
            reliability = self._get_reliability_score(supplier_id)
            lead_time = supplier.get("lead_time_days", 7)
            min_order = supplier.get("minimum_order_qty", 1)
            
            # Calculate composite score: lower cost + higher reliability + shorter lead time
            cost_factor = 1.0 / (unit_cost + 0.01)
            lead_factor = 1.0 / (lead_time + 1)
            
            score = (cost_factor * 0.5) + (reliability * 0.4) + (lead_factor * 0.1)
            
            scored_candidates.append((score, supplier_id, unit_cost, reliability, lead_time, min_order))
        
        if not scored_candidates:
            logger.warning(f"No valid suppliers for SKU {sku_id} at order qty {order_qty}")
            return None
        
        # Select best supplier
        best_score, best_supplier_id, unit_cost, reliability, lead_time, min_order = max(
            scored_candidates, key=lambda x: x[0]
        )
        
        supplier_name = self.suppliers[best_supplier_id].get("supplier_name", "Unknown")
        
        supplier_info = SupplierInfo(
            supplier_id=best_supplier_id,
            supplier_name=supplier_name,
            sku_id=sku_id,
            unit_cost=unit_cost,
            lead_time_days=lead_time,
            min_order_qty=min_order,
            reliability_score=reliability,
        )
        
        logger.info(
            f"Selected supplier {supplier_name} for SKU {sku_id}: "
            f"cost=${unit_cost:.2f}, lead_time={lead_time}d, reliability={reliability:.2f}"
        )
        return supplier_info
