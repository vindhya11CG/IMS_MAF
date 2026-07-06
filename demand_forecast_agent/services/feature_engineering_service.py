"""
FeatureEngineeringService
--------------------------
Single source of truth for feature engineering. It is imported by BOTH:

  1. The training pipeline (training_models/data_preparation.py), which runs
     it in batch over the full historical CSV.
  2. The live agent (demand_forecast_workflow_service.py), which runs it over
     a single-row inference payload coming from an API/service call.

This is the fix for the biggest bug in the original code: the training
pipeline engineered one set of features (lag/rolling windows, string-based
category encoding, columns like `stock_level`/`item_id`/`unit_price` that
don't exist in the real dataset) while the live agent engineered a totally
different set (`stock_gap`, `available_stock`, etc., on real column names).
Because both paths never shared code, the model that got trained never
matched what the agent could actually feed it at inference time - so
inference silently produced wrong-shaped input, or crashed.

Every feature below is intentionally something computable from a SINGLE ROW
(no groupby/shift/rolling), because that's all a live inference request ever
has available. Lag/rolling features were removed rather than "faked" at
inference, since silently filling them with 0 would quietly bias
predictions without anyone noticing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class FeatureEngineeringService:
    """Derives model-ready features from either a raw payload dict
    (single inference request) or a raw historical DataFrame (training)."""

    # Fixed, ordered list of features the model is trained on and expects
    # at inference. Both training and inference reindex onto this exact
    # list (see training_models/model_training.py: XGBoostModel.prepare_features)
    # so the model always receives the same columns, in the same order,
    # regardless of which extra raw fields happen to be present on a row.
    MODEL_FEATURES = [
        "month", "quarter", "day_of_year", "month_sin", "month_cos",
        "is_promotional_int",
        "on_hand_qty", "allocated_qty", "safety_stock_qty", "reorder_point_qty",
        "stock_gap", "available_stock", "safety_ratio", "velocity_score",
        "avg_retail_price", "holding_cost_per_unit_day", "handling_cost_per_unit",
        "order_fulfillment_rate", "total_orders_last_month", "turnover_ratio",
        "demand_std_dev", "lead_time_days", "season_multiplier",
        "category_id", "velocity_class_id",
    ]

    def execute(self, df):

        # Convert dictionary payload to DataFrame
        if isinstance(df, dict):
            df = pd.DataFrame([df])
        elif isinstance(df, pd.DataFrame):
            df = df.copy()
        else:
            raise TypeError(
                "FeatureEngineeringService expects dict or pandas DataFrame."
            )

        # -----------------------
        # Temporal features (derivable from a single row - no lookback)
        # -----------------------
        if "date" in df.columns:
            parsed_date = pd.to_datetime(df["date"], errors="coerce")
            parsed_date = parsed_date.fillna(pd.Timestamp.now())
        else:
            parsed_date = pd.Series([pd.Timestamp.now()] * len(df), index=df.index)

        df["month"] = parsed_date.dt.month
        df["quarter"] = parsed_date.dt.quarter
        df["day_of_year"] = parsed_date.dt.dayofyear
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

        # -----------------------
        # Inventory gap
        # -----------------------
        if "on_hand_qty" in df.columns and "reorder_point_qty" in df.columns:
            df["stock_gap"] = df["on_hand_qty"] - df["reorder_point_qty"]

        # -----------------------
        # Available stock
        # -----------------------
        if "on_hand_qty" in df.columns and "allocated_qty" in df.columns:
            df["available_stock"] = df["on_hand_qty"] - df["allocated_qty"]

        # -----------------------
        # Safety ratio
        # -----------------------
        if "safety_stock_qty" in df.columns and "on_hand_qty" in df.columns:
            df["safety_ratio"] = df["safety_stock_qty"] / (df["on_hand_qty"].abs() + 1)

        # -----------------------
        # Velocity score
        # -----------------------
        if "annual_units_max" in df.columns:
            df["velocity_score"] = np.log1p(df["annual_units_max"])

        # -----------------------
        # Promotional flag -> numeric (CSV stores True/False as strings/bools)
        # -----------------------
        if "is_promotional" in df.columns:
            df["is_promotional_int"] = (
                df["is_promotional"]
                .astype(str)
                .str.lower()
                .isin(["true", "1", "yes"])
                .astype(int)
            )

        return df

    def to_model_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reindex an already-engineered DataFrame onto the fixed
        MODEL_FEATURES column set/order, filling anything missing with 0.
        This is what guarantees train/inference shape parity."""
        return df.reindex(columns=self.MODEL_FEATURES, fill_value=0)
