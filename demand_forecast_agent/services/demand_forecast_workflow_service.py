from agent_framework import Agent
import pandas as pd
import os

from demand_forecast_agent.services.forecast_service import ForecastService
from demand_forecast_agent.services.confidence_service import ConfidenceService
from demand_forecast_agent.services.output_formatter_service import OutputFormatterService
from demand_forecast_agent.services.explanation_service import ExplanationService

from demand_forecast_agent.services.feature_engineering_service import create_features
from demand_forecast_agent.services.inventory_decision_service import get_inventory_decision
from demand_forecast_agent.services.reorder_service import calculate_reorder
from demand_forecast_agent.services.logging_service import log_prediction


class DemandForecastWorkflow(Agent):

    async def run(
        self,
        item_id,
        horizon
    ):

        data = pd.read_parquet(
            os.getenv("DATA_PATH")
        )

        row = (
            data[
                data["item_id"]
                ==
                item_id
            ]
            .tail(1)
        )

        row = create_features(row)

        stock = float(
            row.iloc[0]["stock_level"]
        )

        forecast = (
            ForecastService()
            .execute(
                item_id,
                horizon
            )
        )

        confidence = (
            ConfidenceService()
            .execute()
        )

        decision = (
            get_inventory_decision(
                forecast,
                stock
            )
        )

        reorder = (
            calculate_reorder(
                forecast,
                stock
            )
        )

        log_prediction(
            row.to_dict(),
            forecast
        )

        explanation = (
            ExplanationService()
            .execute(
                item_id,
                forecast,
                confidence
            )
        )

        result = (
            OutputFormatterService()
            .execute(
                item_id,
                forecast,
                confidence,
                horizon,
                explanation
            )
        )

        return {
            "forecast": result[0],
            "explanation": result[1],
            "inventory_decision": decision,
            "recommended_reorder": reorder
        }