from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from ..models import (
    InventoryPosition,
    InventoryCalculationResult,
    RiskAssessment,
    WeatherFestivalContext,
)
from .base_service import AgentService

logger = logging.getLogger(__name__)


class InventoryRiskMonitoringService(AgentService):
    """Service that evaluates stock risk for inventory positions.

    Phase 6 extension: when a ``weather_context_map`` is supplied, each
    assessment is enriched with weather/festival signals that:
    - Scale the effective forecasted demand by the weather demand multiplier.
    - Add risk reason strings for extreme weather or festival proximity.
    - Attach the ``WeatherFestivalContext`` to the ``RiskAssessment`` so
      downstream agents (replenishment planning, supplier selection) can
      use it without re-loading the dataset.

    Fully backward-compatible: ``weather_context_map=None`` (the default)
    leaves the assessment logic identical to the original pre-weather version.
    """

    def __init__(self) -> None:
        super().__init__(name="InventoryRiskMonitoringService")

    def execute(
        self,
        positions: Iterable[InventoryPosition],
        calculation_results: Iterable[InventoryCalculationResult],
        in_transit_data: Iterable[dict],
        forecasted_demand: dict[tuple[int, int], int],
        weather_context_map: Optional[Dict[tuple[int, int], WeatherFestivalContext]] = None,
    ) -> List[RiskAssessment]:
        """Execute risk assessment."""
        return self.assess_risk(
            list(positions),
            list(calculation_results),
            list(in_transit_data),
            forecasted_demand,
            weather_context_map=weather_context_map,
        )

    def assess_risk(
        self,
        positions: List[InventoryPosition],
        calculation_results: List[InventoryCalculationResult],
        in_transit_data: List[dict],
        forecasted_demand: dict[tuple[int, int], int],
        weather_context_map: Optional[Dict[tuple[int, int], WeatherFestivalContext]] = None,
    ) -> List[RiskAssessment]:
        """Assess inventory risk for all positions."""
        transit_map = self._group_in_transit_quantities(in_transit_data)
        result_map = {
            (result.sku_id, result.location_id): result
            for result in calculation_results
        }
        wx_map = weather_context_map or {}

        assessments: List[RiskAssessment] = []
        for position in positions:
            key = (position.sku_id, position.location_id)
            current_stock = result_map.get(key, InventoryCalculationResult(
                sku_id=position.sku_id,
                location_id=position.location_id,
                current_stock=position.on_hand_qty,
                previous_stock=position.on_hand_qty,
                sales=0,
                incoming_stock=0,
                adjustments=0,
                source="inventory_positions",
            )).current_stock

            in_transit_qty = transit_map.get(key, 0)
            base_forecast = forecasted_demand.get(key, 0)

            # --- Weather/festival enrichment ---
            wx_ctx = wx_map.get(key)
            if wx_ctx is not None:
                effective_multiplier = wx_ctx.effective_demand_multiplier()
                forecast = int(math.ceil(base_forecast * effective_multiplier))
            else:
                forecast = base_forecast

            projected_stock = current_stock + in_transit_qty - forecast
            risk_reasons: list[str] = []

            if current_stock <= position.reorder_point_qty:
                risk_reasons.append("Current stock is at or below reorder point.")
            if current_stock <= position.safety_stock_qty:
                risk_reasons.append("Current stock is at or below safety stock.")
            if projected_stock < position.safety_stock_qty:
                risk_reasons.append("Projected stock falls below safety stock after forecasted demand.")

            # Weather/festival risk reasons
            if wx_ctx is not None:
                wx_risk_reasons = wx_ctx.describe_risks()
                risk_reasons.extend(wx_risk_reasons)
                # High weather/festival risk can trigger risk_detected even if
                # stock levels appear adequate, because demand may spike before
                # the next replenishment window.
                if wx_ctx.is_high_risk() and not any(
                    r.startswith("Current stock") or r.startswith("Projected stock")
                    for r in risk_reasons
                ):
                    risk_reasons.append(
                        "Weather/festival conditions indicate elevated demand or supply disruption "
                        "risk — pre-emptive replenishment recommended."
                    )

            risk_detected = len(risk_reasons) > 0
            recommended_action = (
                "Trigger replenishment review and notify planning agent."
                if risk_detected
                else "No replenishment needed; continue monitoring."
            )

            assessment = RiskAssessment(
                sku_id=position.sku_id,
                location_id=position.location_id,
                current_stock=current_stock,
                safety_stock=position.safety_stock_qty,
                reorder_point=position.reorder_point_qty,
                in_transit_qty=in_transit_qty,
                forecasted_demand=forecast,
                projected_stock=projected_stock,
                risk_detected=risk_detected,
                risk_reasons=risk_reasons,
                recommended_action=recommended_action,
                weather_context=wx_ctx,
            )
            assessments.append(assessment)
            
            if risk_detected:
                logger.warning(
                    f"Risk detected for SKU {position.sku_id} @ Location {position.location_id}: "
                    f"current_stock={current_stock}, safety_stock={position.safety_stock_qty}"
                    + (f", weather_multiplier={wx_ctx.effective_demand_multiplier():.2f}" if wx_ctx else "")
                )

        logger.info(f"Risk assessment completed for {len(assessments)} positions")
        wx_enriched = sum(1 for a in assessments if a.weather_context is not None)
        if wx_enriched:
            logger.info(f"  {wx_enriched} assessments enriched with weather/festival context")
        return assessments

    def estimate_forecasted_demand(
        self,
        calculation_results: Iterable[InventoryCalculationResult],
        lookback_periods: int = 4,
    ) -> dict[tuple[int, int], int]:
        """
        Estimate forecasted demand using recent sales history.
        
        FIXED: Now properly uses lookback_periods parameter to only consider recent data.
        """
        demand_totals: dict[tuple[int, int], list[int]] = defaultdict(list)

        for result in calculation_results:
            demand_totals[(result.sku_id, result.location_id)].append(result.sales)

        # FIXED: Apply lookback_periods filter to use only recent data
        forecasted_demand = {}
        for key, values in demand_totals.items():
            # Use only the most recent lookback_periods records
            recent_values = values[-lookback_periods:] if len(values) > 0 else values
            if recent_values:
                forecast = math.ceil(sum(recent_values) / len(recent_values))
                forecasted_demand[key] = forecast
                logger.debug(
                    f"Forecasted demand for SKU {key[0]} @ Location {key[1]}: {forecast} "
                    f"(from {len(recent_values)} recent periods)"
                )
            else:
                forecasted_demand[key] = 0

        return forecasted_demand

    def _group_in_transit_quantities(self, in_transit_data: Iterable[dict]) -> dict[tuple[int, int], int]:
        """Group in-transit quantities by SKU and location."""
        grouped: dict[tuple[int, int], int] = defaultdict(int)
        for row in in_transit_data:
            sku_id = row.get("sku_id", 0)
            location_id = row.get("location_id", 0)
            
            # Validate data
            if sku_id == 0 or location_id == 0:
                logger.warning(f"Invalid in-transit data: sku_id={sku_id}, location_id={location_id}")
                continue
            
            key = (sku_id, location_id)
            quantity = int(row.get("quantity_in_transit", 0) or 0)
            grouped[key] += quantity
            
        return dict(grouped)
