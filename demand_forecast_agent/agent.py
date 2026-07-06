import asyncio

from demand_forecast_agent.services.demand_forecast_workflow_service import (
    DemandForecastWorkflow
)


class DemandForecastAgent:

    def execute(

        self,

        payload,

        horizon=14

    ):

        return (

            asyncio.run(

                DemandForecastWorkflow()

                .run(

                    payload,

                    horizon

                )

            )

        )