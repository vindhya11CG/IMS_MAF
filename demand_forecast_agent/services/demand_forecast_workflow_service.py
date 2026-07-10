from demand_forecast_agent.services.core_forecasting_service import (
    ForecastService,
    ConfidenceService,
    LoggingService,
)
from demand_forecast_agent.services.azure_services import ExplanationService
from demand_forecast_agent.services.feature_engineering_service import (
    FeatureEngineeringService,
)
from demand_forecast_agent.services.decision_services import (
    InventoryDecisionService,
    ReorderService,
    InputValidatorService,
    OutputFormatterService,
)


class DemandForecastWorkflow:

    async def run(self, payload, horizon=14):

        validation = InputValidatorService().execute(payload)

        if not validation["valid"]:
            return validation

        # Feature-engineer the raw payload once. `engineered` carries both
        # the original raw fields and the derived features - the model
        # matrix is built from it just before calling the model (see
        # ForecastService), so it stays as the single object flowing
        # through the rest of the workflow too.
        engineered = FeatureEngineeringService().execute(payload)

        forecast = ForecastService().execute(
            engineered,
            horizon,
            product_id=payload["product_id"],
        )

        if forecast["status"] != "SUCCESS":
            return forecast

        prediction = forecast["forecast"]

        confidence = ConfidenceService().execute()

        decision = InventoryDecisionService().execute(
            prediction,
            payload["on_hand_qty"],
            payload["reorder_point_qty"],
            payload["safety_stock_qty"],
        )

        reorder = ReorderService().execute(
            prediction,
            payload["on_hand_qty"],
            payload.get("allocated_qty", 0),
            payload["safety_stock_qty"],
        )

        LoggingService().execute({
            "payload": payload,
            "forecast": prediction,
        })

        explanation = ExplanationService().execute(
            payload["product_id"],
            prediction,
            confidence,
        )

        return OutputFormatterService().execute(
            payload["product_id"],
            prediction,
            confidence,
            horizon,
            explanation,
            decision,
            reorder,
        )
