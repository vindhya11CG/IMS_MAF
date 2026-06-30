import pandas as pd
import numpy as np

class FeatureEngineeringService:

    def execute(self, df):

        if "stock_level" in df.columns and "reorder_point" in df.columns:
            df["stock_gap"] = (
                df["stock_level"]
                - df["reorder_point"]
            )

        if (
            "demand_std_dev" in df.columns
            and "daily_demand" in df.columns
        ):
            df["demand_variability"] = (
                np.log1p(
                    df["demand_std_dev"]
                    /
                    (
                        df["daily_demand"]
                        + 1
                    )
                )
            )

        if (
            "stockout_count_last_month"
            in df.columns
            and
            "total_orders_last_month"
            in df.columns
        ):
            df["stockout_risk"] = (
                df["stockout_count_last_month"]
                /
                (
                    df["total_orders_last_month"]
                    + 1
                )
            )

        return df