"""
Consolidated: ModelLoaderService + ForecastService + BatchForecastService +
ConfidenceService + LoggingService

Updated for event-driven demand forecasting with weather, festival, weekend,
and warehouse risk multipliers.
"""
import datetime
import json
import os
import warnings
from pathlib import Path

import pandas as pd

from .feature_engineering_service import FeatureEngineeringService


class ModelLoaderService:

    _instance = None

    @classmethod
    def load(cls):
        if cls._instance:
            return cls._instance

        path = Path(os.getenv("MODEL_PATH", "training_models/hybrid_model.pkl"))

        if not path.exists():
            raise FileNotFoundError(f"Model missing: {path}")

        import joblib

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cls._instance = joblib.load(path)
        return cls._instance

    @classmethod
    def reset(cls):
        """Test helper: forces the next load() to re-read from disk."""
        cls._instance = None


class ConfidenceService:

    @staticmethod
    def _normalise_confidence(raw_confidence):
        try:
            confidence = float(str(raw_confidence).strip().rstrip("%"))
        except (TypeError, ValueError):
            return 90.0

        if 0 <= confidence <= 1:
            confidence *= 100.0

        if confidence < 0:
            confidence = 0.0
        elif confidence > 100:
            confidence = 100.0

        return round(confidence, 2)

    def execute(self):
        metrics_path = os.getenv("METRICS_PATH", "training_models/model_metrics.json")
        if metrics_path and os.path.exists(metrics_path):
            try:
                with open(metrics_path, "r", encoding="utf-8") as f:
                    metrics = json.load(f)
                raw_confidence = metrics.get("test_metrics", {}).get("Accuracy_pct", 90.0)
                return self._normalise_confidence(raw_confidence)
            except Exception:
                pass
        return 90.0


class ForecastService:

    def __init__(self):
        self.model = ModelLoaderService.load()
        self.engineer = FeatureEngineeringService()

    def _contextual_forecast(self, engineered_df: pd.DataFrame, horizon, product_id):
        """Blend model inference with weather, festival, and weekend context."""
        if engineered_df is None or engineered_df.empty:
            return None

        try:
            row = engineered_df.iloc[0]
            product_id = int(product_id)
            location_id = int(row.get("location_id", 0) or 0)

            context_path = Path(
                os.getenv(
                    "DB6_CONTEXT_PATH",
                    "data/csv_exports/db6_csv_export/demand_context_fact.csv",
                )
            )
            anchor = 25.0
            if context_path.exists():
                try:
                    context_df = pd.read_csv(context_path)
                    candidates = context_df[
                        (context_df["product_id"].astype(int) == product_id)
                        & (context_df["location_id"].astype(int) == location_id)
                    ]
                    if not candidates.empty:
                        context_row = candidates.iloc[0]
                        for key in [
                            "weather_adjusted_demand",
                            "regional_adjusted_demand",
                            "daily_demand_pre_festival_adjustment",
                        ]:
                            if key in context_row.index and pd.notna(context_row.get(key)):
                                val = float(context_row.get(key))
                                if val > 0:
                                    anchor = val
                                    break
                except Exception:
                    pass

            multiplier = 1.0
            if "festival_demand_lift_pct" in row.index and float(row.get("festival_demand_lift_pct", 0.0) or 0.0) > 0:
                lift = float(row.get("festival_demand_lift_pct", 0.0))
                multiplier *= 1.0 + (lift / 100.0)
            elif "is_festival_day_int" in row.index and float(row.get("is_festival_day_int", 0) or 0) == 1:
                multiplier *= 1.45

            if "weather_demand_multiplier" in row.index:
                multiplier *= max(0.5, float(row.get("weather_demand_multiplier", 1.0) or 1.0))
            if "festival_proximity_score" in row.index:
                multiplier *= 1.0 + (float(row.get("festival_proximity_score", 0.0) or 0.0) * 0.6)
            if "is_shopping_season_int" in row.index:
                multiplier *= 1.0 + (float(row.get("is_shopping_season_int", 0) or 0) * 0.2)
            if "is_weekend" in row.index and float(row.get("is_weekend", 0) or 0) == 1:
                multiplier *= 1.25
            if "supply_disruption_risk" in row.index:
                multiplier *= 1.0 + (float(row.get("supply_disruption_risk", 0.0) or 0.0) * 0.15)

            return round(max(1.0, anchor * multiplier), 2)
        except Exception:
            return None

    def execute(self, engineered_df: pd.DataFrame, horizon, product_id):
        try:
            model_input = self.engineer.to_model_matrix(engineered_df)

            prediction = self.model.forecast(
                model_input,
                steps_ahead=horizon,
                item_id=str(product_id),
            )
            model_forecast = round(float(prediction.mean()), 2)
            contextual_forecast = self._contextual_forecast(engineered_df, horizon, product_id)

            if contextual_forecast is None:
                forecast = model_forecast
            else:
                forecast = round((model_forecast * 0.6) + (contextual_forecast * 0.4), 2)

            # Apply explicit festival demand lift override if present
            if engineered_df is not None and not engineered_df.empty:
                row = engineered_df.iloc[0]
                lift = float(row.get("festival_demand_lift_pct", 0.0) or 0.0)
                if lift > 0:
                    forecast = round(forecast * (1.0 + lift / 100.0), 2)
                elif float(row.get("is_festival_day_int", 0) or 0) == 1:
                    forecast = round(forecast * 1.4, 2)

            return {
                "status": "SUCCESS",
                "forecast": max(1.0, forecast),
            }

        except Exception as e:
            return {
                "status": "FORECAST_FAILED",
                "message": str(e),
            }


class BatchForecastService:

    def execute(self, model, rows, features, engineer):
        df = pd.DataFrame(rows)
        df = engineer.execute(df)
        df = df.reindex(columns=features, fill_value=0)
        xgb_model = getattr(model, "xgboost_model", model)
        pred = xgb_model.predict(df)
        return [round(max(1.0, float(i)), 2) for i in pred]


class LoggingService:

    def execute(self, payload):
        ts = datetime.datetime.now().isoformat()
        print("\n===== FORECAST LOG =====")
        print(ts)
        print(json.dumps(payload, indent=2, default=str))
        print("========================")
