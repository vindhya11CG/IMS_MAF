import pandas as pd

from .model_loader_service import (
    ModelLoaderService
)


class ForecastService:

    def __init__(self):

        self.model = (
            ModelLoaderService.load()
        )

    def execute(

        self,

        payload,

        horizon

    ):

        try:

            df = pd.DataFrame(
                [payload]
            )

            prediction = (

                self.model.forecast(

                    df,

                    steps_ahead=horizon,

                    item_id=str(
                        payload[
                            "product_id"
                        ]
                    )

                )

            )

            return {

                "status":
                "SUCCESS",

                "forecast":
                round(
                    float(
                        prediction.mean()
                    ),
                    2
                )

            }

        except Exception as e:

            return {

                "status":
                "FORECAST_FAILED",

                "message":
                str(e)

            }