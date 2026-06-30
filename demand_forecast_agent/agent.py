import asyncio

from demand_forecast_agent.services.demand_forecast_workflow_service import (
    DemandForecastWorkflow
)


class DemandForecastAgent:

    def execute(
        self,
        item_id,
        horizon=14
    ):

        return asyncio.run(

            DemandForecastWorkflow()
            .run(
                item_id,
                horizon
            )
        )