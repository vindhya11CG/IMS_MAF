"""
Consolidated: ModelLoaderService + ForecastService + BatchForecastService +
ConfidenceService + LoggingService
(previously 5 separate files)

BUG FIXED HERE (the main reason the demand forecast agent broke at
inference):

The original `ForecastService.execute()` re-wrapped its input with
`pd.DataFrame([payload])`, even when `payload` was already the engineered
DataFrame produced by FeatureEngineeringService. Wrapping a DataFrame
inside a list and handing it back to `pd.DataFrame(...)` does not do what
was intended, and `payload["product_id"]` on a DataFrame returns a Series,
not a scalar - so `item_id=str(payload["product_id"])` was building a
malformed lookup key for the per-item SARIMAX model.

On top of that, `XGBoostModel.predict()` (training_models/model_training.py)
recomputed its feature list from whatever columns happened to be present on
each incoming DataFrame, instead of reindexing onto the fixed column list
it was actually fit on. A single-row inference payload never has the
lag/rolling columns that show up during batch training, so the number of
columns fed into the fitted `StandardScaler`/`XGBRegressor` at inference did
not match what they were fit on -> shape-mismatch crash.

Fix applied in both places:
  * ForecastService now takes the already-engineered DataFrame directly
    (no re-wrapping) and reindexes it onto FeatureEngineeringService.MODEL_FEATURES
    before calling the model - the exact same reindex step
    BatchForecastService was already (correctly) doing.
  * training_models/model_training.py now reindexes onto the same fixed
    feature list at both fit time and predict time (see that file).
"""
import json
import os
import datetime

import pandas as pd

from .feature_engineering_service import FeatureEngineeringService


class ModelLoaderService:

    _instance = None

    @classmethod
    def load(cls):

        if cls._instance:
            return cls._instance

        from pathlib import Path

        path = Path(os.getenv("MODEL_PATH", "training_models/hybrid_model.pkl"))

        if not path.exists():
            raise FileNotFoundError(f"Model missing: {path}")

        import joblib

        cls._instance = joblib.load(path)

        return cls._instance

    @classmethod
    def reset(cls):
        """Test helper: forces the next load() to re-read from disk."""
        cls._instance = None


class ConfidenceService:

    def execute(self):

        with open(os.getenv("METRICS_PATH")) as f:
            metrics = json.load(f)

        return round(metrics["test_metrics"]["Accuracy_pct"], 2)


class ForecastService:

    def __init__(self):
        self.model = ModelLoaderService.load()
        self.engineer = FeatureEngineeringService()

    def execute(self, engineered_df: pd.DataFrame, horizon, product_id):
        """
        Args:
            engineered_df: the already feature-engineered single-row
                DataFrame produced by FeatureEngineeringService.execute().
            horizon: forecast horizon in days.
            product_id: the product id, passed explicitly (not pulled back
                out of the DataFrame) so there is no ambiguity about
                scalar vs. Series.
        """
        try:
            model_input = self.engineer.to_model_matrix(engineered_df)

            prediction = self.model.forecast(
                model_input,
                steps_ahead=horizon,
                item_id=str(product_id),
            )

            return {
                "status": "SUCCESS",
                "forecast": round(float(prediction.mean()), 2),
            }

        except Exception as e:
            return {
                "status": "FORECAST_FAILED",
                "message": str(e),
            }


class BatchForecastService:
    """Batch/bulk scoring path - deliberately XGBoost-only (no per-item
    SARIMAX lookups), since SARIMAX in this codebase is fit per product_id
    and calling it per-row for a large batch would be far too slow for a
    bulk endpoint. This mirrors how HybridDemandForecaster.forecast() itself
    falls back to the XGBoost-only prediction whenever no SARIMAX model
    exists for a given product.

    BUG FIXED: this used to call `model.predict(df)` directly on the
    *loaded* model object, but ModelLoaderService.load() returns the
    HybridDemandForecaster, which only exposes `.forecast(df, steps_ahead,
    item_id)` - it has no `.predict()` method. `.predict()` lives on the
    inner `.xgboost_model`. Calling `.predict()` on the wrong object raised
    an AttributeError on every batch request.
    """

    def execute(self, model, rows, features, engineer):

        df = pd.DataFrame(rows)

        df = engineer.execute(df)

        df = df.reindex(columns=features, fill_value=0)

        xgb_model = getattr(model, "xgboost_model", model)
        pred = xgb_model.predict(df)

        return [round(float(i), 2) for i in pred]


class LoggingService:

    def execute(self, payload):

        ts = datetime.datetime.now().isoformat()

        print("\n===== FORECAST LOG =====")
        print(ts)
        print(json.dumps(payload, indent=2, default=str))
        print("========================")
