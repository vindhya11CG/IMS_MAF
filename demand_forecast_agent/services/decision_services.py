"""
Consolidated: InputValidatorService + InventoryDecisionService + ReorderService
+ OutputFormatterService

PATCH (this pass): OutputFormatterService now builds ForecastResult with
`forecasted_demand=...` instead of `forecast_demand=...`, matching the
rename in demand_forecast_agent/models/forecast_models.py. This is the fix
for the field-name mismatch against agents/inventory_monitoring/models
.RiskAssessment.forecasted_demand flagged in the previous pass - done
entirely inside demand_forecast_agent's own files.

Everything else here is unchanged from the previous consolidated version -
the validator/decision/reorder logic already matched the training dataset
and DB3 inventory_positions column names (product_id, location_id,
on_hand_qty, allocated_qty, reorder_point_qty, safety_stock_qty).
"""
from demand_forecast_agent.models.forecast_models import ForecastResult


class InputValidatorService:

    REQUIRED = [
        "product_id",
        "location_id",
        "on_hand_qty",
        "allocated_qty",
        "reorder_point_qty",
        "safety_stock_qty",
    ]

    def execute(self, payload):

        missing = [f for f in self.REQUIRED if f not in payload]

        if missing:
            return {
                "valid": False,
                "message": "Missing fields: " + ",".join(missing),
            }

        numeric = ["on_hand_qty", "reorder_point_qty", "safety_stock_qty"]

        for col in numeric:
            if payload[col] < 0:
                return {
                    "valid": False,
                    "message": f"{col} cannot be negative",
                }

        return {"valid": True}


class InventoryDecisionService:

    def execute(self, forecast, stock, reorder_point, safety_stock):

        projected = stock - forecast

        if projected <= reorder_point:
            return {"decision": "REORDER_IMMEDIATELY", "severity": "HIGH"}

        if projected <= (reorder_point + safety_stock):
            return {"decision": "MONITOR", "severity": "MEDIUM"}

        return {"decision": "SAFE", "severity": "LOW"}


class ReorderService:

    def execute(self, forecast, stock, allocated, safety, transit=0):

        available = stock - allocated + transit

        qty = forecast + safety - available

        return round(max(qty, 0), 2)


class OutputFormatterService:

    def execute(
        self,
        item,
        forecast,
        confidence,
        horizon,
        explanation,
        inventory=None,
        reorder=None,
    ):

        result = ForecastResult(
            item_id=item,
            forecasted_demand=round(forecast, 2),
            confidence=confidence,
            model_used="Hybrid SARIMAX+XGBoost",
            horizon_days=horizon,
        )

        return {
            "forecast": result,
            "inventory_decision": inventory,
            "recommended_reorder": reorder,
            "explanation": explanation,
        }
