"""
PATCH: ForecastResult.forecast_demand renamed to ForecastResult.forecasted_demand
so it matches RiskAssessment.forecasted_demand (agents/inventory_monitoring/models)
field-for-field.

This resolves the integration issue flagged in the previous fix pass:
"OutputFormatterService returns a ForecastResult with field forecast_demand.
The Inventory Monitoring Agent's RiskAssessment dataclass expects
forecasted_demand - a different name."

Fixed entirely inside demand_forecast_agent's own model file. Nothing in
agents/inventory_monitoring, agents/replenishment_planning, or
agents/supplier_selection was touched.
"""
from dataclasses import dataclass


@dataclass
class ForecastRequest:
    item_id: str
    horizon_days: int


@dataclass
class ForecastResult:
    item_id: str
    forecasted_demand: float
    confidence: float
    model_used: str
    horizon_days: int
