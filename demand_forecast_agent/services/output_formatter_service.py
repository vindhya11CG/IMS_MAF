from demand_forecast_agent.models.forecast_models import (
    ForecastResult
)


class OutputFormatterService:

    def execute(
        self,
        item,
        forecast,
        confidence,
        horizon,
        explanation
    ):

        return ForecastResult(

            item_id=item,

            forecast_demand=round(
                forecast,
                2
            ),

            confidence=confidence,

            model_used=(
                "Hybrid SARIMAX+XGBoost"
            ),

            horizon_days=horizon
        ), explanation