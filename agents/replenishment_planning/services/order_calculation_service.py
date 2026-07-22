"""Order calculation service for replenishment planning.

Phase 6 extension: when a RiskAssessment carries a WeatherFestivalContext,
the EOQ calculation uses the effective demand multiplier to scale annual
demand, and the order priority can be elevated to URGENT for extreme
weather or high supply-disruption risk regardless of stock level.
"""

from __future__ import annotations

import logging
import math
from typing import List

from agents.inventory_monitoring.models import RiskAssessment
from .base_service import ReplenishmentService
from ..models import OrderRecommendation, ReplenishmentOrder, SupplierInfo

logger = logging.getLogger(__name__)


class OrderCalculationService(ReplenishmentService):
    """Calculates optimal order quantities and generates replenishment orders."""

    def __init__(
        self,
        holding_cost_per_unit: float = 2.5,
        ordering_cost: float = 50.0,
    ) -> None:
        super().__init__(name="OrderCalculationService")
        self.holding_cost_per_unit = holding_cost_per_unit
        self.ordering_cost = ordering_cost

    def calculate_eoq(
        self,
        annual_demand: int,
        unit_cost: float,
    ) -> int:
        """
        Calculate Economic Order Quantity (EOQ).
        
        EOQ = sqrt((2 * D * S) / (H * C))
        where:
            D = Annual demand
            S = Ordering cost per order
            H = Holding cost per unit
            C = Unit cost
        
        Returns: EOQ quantity (minimum 1)
        """
        if annual_demand <= 0 or unit_cost <= 0:
            return 1

        numerator = 2 * annual_demand * self.ordering_cost
        denominator = self.holding_cost_per_unit * unit_cost
        
        if denominator <= 0:
            return 1

        eoq = math.sqrt(numerator / denominator)
        return max(1, int(eoq))

    def estimate_annual_demand(
        self,
        forecasted_demand: int,
        days_in_period: int = 30,
    ) -> int:
        """Estimate annual demand from recent forecast (30-day period)."""
        if days_in_period <= 0:
            return forecasted_demand
        annual = (forecasted_demand / max(days_in_period, 1)) * 365
        return max(1, int(annual))

    def calculate_order_priority(
        self,
        current_stock: int,
        reorder_point: int,
        safety_stock: int,
    ) -> str:
        """Determine order priority based on stock levels."""
        if current_stock <= safety_stock:
            return "URGENT"
        elif current_stock <= reorder_point:
            return "HIGH"
        else:
            return "MEDIUM"

    def generate_order(
        self,
        assessment: RiskAssessment,
        supplier: SupplierInfo,
        order_id: str,
    ) -> ReplenishmentOrder:
        """Generate a replenishment order from a risk assessment and supplier info."""
        
        # Estimate annual demand — optionally scaled by weather/festival context
        wx = assessment.weather_context
        demand_multiplier = 1.0
        if wx is not None:
            demand_multiplier = wx.effective_demand_multiplier()

        base_annual_demand = self.estimate_annual_demand(assessment.forecasted_demand)
        adjusted_annual_demand = max(1, int(base_annual_demand * demand_multiplier))
        
        # Calculate EOQ using weather-adjusted demand
        eoq = self.calculate_eoq(adjusted_annual_demand, supplier.unit_cost)
        
        # Order quantity is max of EOQ and minimum supplier requirement
        order_qty = max(eoq, supplier.min_order_qty)
        
        # Calculate costs
        total_cost = order_qty * supplier.unit_cost
        
        # Determine priority — weather can elevate to URGENT
        priority = self.calculate_order_priority(
            assessment.current_stock,
            assessment.reorder_point,
            assessment.safety_stock,
        )
        if wx is not None and priority != "URGENT":
            if wx.extreme_weather_flag or wx.supply_disruption_risk > 0.7:
                priority = "URGENT"
            elif wx.is_high_risk() and priority == "MEDIUM":
                priority = "HIGH"
        
        # Build reasoning
        reasoning = (
            f"Stock at {assessment.current_stock} (reorder: {assessment.reorder_point}, "
            f"safety: {assessment.safety_stock}). "
            f"EOQ: {eoq} + supplier min: {supplier.min_order_qty} = {order_qty} units. "
            f"Lead time: {supplier.lead_time_days} days. Cost: ${total_cost:.2f}"
        )
        if wx is not None and demand_multiplier != 1.0:
            reasoning += (
                f" [Weather/Festival: demand multiplier {demand_multiplier:.2f}×, "
                f"severity={wx.weather_severity_index:.2f}"
            )
            if wx.is_festival_day:
                reasoning += f", festival_day=True (proximity={wx.festival_proximity_score:.2f})"
            if wx.extreme_weather_flag:
                reasoning += ", EXTREME_WEATHER"
            reasoning += "]"
        
        return ReplenishmentOrder(
            order_id=order_id,
            sku_id=assessment.sku_id,
            location_id=assessment.location_id,
            current_stock=assessment.current_stock,
            reorder_point=assessment.reorder_point,
            safety_stock=assessment.safety_stock,
            order_quantity=order_qty,
            unit_cost=supplier.unit_cost,
            total_cost=total_cost,
            supplier_id=supplier.supplier_id,
            supplier_name=supplier.supplier_name,
            lead_time_days=supplier.lead_time_days,
            order_priority=priority,
            reasoning=reasoning,
        )

    def execute(
        self,
        risky_assessments: List[RiskAssessment],
        suppliers: dict[int, SupplierInfo],
    ) -> List[ReplenishmentOrder]:
        """
        Generate replenishment orders for all risky items.
        
        Args:
            risky_assessments: List of risk assessments with risk_detected=True
            suppliers: Dict mapping sku_id to SupplierInfo
            
        Returns:
            List of generated ReplenishmentOrder objects
        """
        orders = []
        
        for idx, assessment in enumerate(risky_assessments, 1):
            supplier = suppliers.get(assessment.sku_id)
            if not supplier:
                logger.warning(f"No supplier found for SKU {assessment.sku_id}, skipping")
                continue
            
            order_id = f"ORD-{assessment.location_id:04d}-{assessment.sku_id:06d}-{idx:03d}"
            order = self.generate_order(assessment, supplier, order_id)
            orders.append(order)
        
        logger.info(f"Generated {len(orders)} replenishment orders")
        return orders
