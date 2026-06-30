import os
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
        item_id,
        horizon_days,
        location=None
    ):

        data = pd.read_parquet(
            os.getenv(
                "DATA_PATH"
            )
        )

        data = (
            data
            .sort_values(
                "date"
            )
        )

        subset = (
            data[
                data["item_id"]
                == item_id
            ]
            .tail(
                horizon_days
            )
        )

        if subset.empty:
            return {
                "status": "NO_ITEM_FOUND",
                "message": f"No data found for item_id: {item_id}",
                "forecast": None
            }

        prediction = (
            self.model.forecast(
                subset,
                steps_ahead=horizon_days,
                item_id=item_id
            )
        )

        return {
            "status": "SUCCESS",
            "forecast": round(
                float(
                    prediction.mean()
                ),
                2
            )
}