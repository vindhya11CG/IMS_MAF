from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, List

from .models import InventoryPosition, InventoryCalculationResult, RiskAssessment
from .service_base import AgentService


class InventoryRiskMonitoringService(AgentService):
    """Service that evaluates stock risk for inventory positions."""

    def __init__(self) -> None:
        super().__init__(name="InventoryRiskMonitoringService")

    def execute(
        self,
        positions: Iterable[InventoryPosition],
        calculation_results: Iterable[InventoryCalculationResult],
        in_transit_data: Iterable[dict],
        forecasted_demand: dict[tuple[int, int], int],
    ) -> List[RiskAssessment]:
        return self.assess_risk(
            list(positions),
            list(calculation_results),
            list(in_transit_data),
            forecasted_demand,
        )

    def assess_risk(
        self,
        positions: List[InventoryPosition],
        calculation_results: List[InventoryCalculationResult],
        in_transit_data: List[dict],
        forecasted_demand: dict[tuple[int, int], int],
    ) -> List[RiskAssessment]:
        transit_map = self._group_in_transit_quantities(in_transit_data)
        result_map = {
            (result.sku_id, result.location_id): result
            for result in calculation_results
        }

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
            forecast = forecasted_demand.get(key, 0)
            projected_stock = current_stock + in_transit_qty - forecast
            risk_reasons: list[str] = []

            if current_stock <= position.reorder_point_qty:
                risk_reasons.append("Current stock is at or below reorder point.")
            if current_stock <= position.safety_stock_qty:
                risk_reasons.append("Current stock is at or below safety stock.")
            if projected_stock < position.safety_stock_qty:
                risk_reasons.append("Projected stock falls below safety stock after forecasted demand.")

            risk_detected = len(risk_reasons) > 0
            recommended_action = (
                "Trigger replenishment review and notify planning agent."
                if risk_detected
                else "No replenishment needed; continue monitoring."
            )

            assessments.append(
                RiskAssessment(
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
                )
            )

        return assessments

    def estimate_forecasted_demand(
        self,
        snapshots: Iterable[InventoryCalculationResult],
        lookback_periods: int = 4,
    ) -> dict[tuple[int, int], int]:
        demand_totals: dict[tuple[int, int], list[int]] = defaultdict(list)

        for snapshot in snapshots:
            demand_totals[(snapshot.sku_id, snapshot.location_id)].append(snapshot.sales)

        return {
            key: math.ceil(sum(values) / max(len(values), 1))
            for key, values in demand_totals.items()
        }

    def _group_in_transit_quantities(self, in_transit_data: Iterable[dict]) -> dict[tuple[int, int], int]:
        grouped: dict[tuple[int, int], int] = defaultdict(int)
        for row in in_transit_data:
            key = (row.get("sku_id", 0), row.get("location_id", 0))
            grouped[key] += int(row.get("quantity_in_transit", 0) or 0)
        return grouped
