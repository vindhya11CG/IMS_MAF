"""
SARIMAX + XGBoost Hybrid Demand Forecasting Model - model classes only.

WHY THIS FILE EXISTS (fixes the joblib/pickle AttributeError)
----------------------------------------------------------------
These classes used to live directly inside `model_training.py`. When that
file is run as a script (`python training_models/model_training.py`),
Python executes it as the `__main__` module - so `joblib.dump(model, ...)`
pickled `HybridDemandForecaster` with the module reference `__main__`.

Any OTHER process that later tries to unpickle that file (e.g.
`tests/test_demand_forecast_agent.py`, or the live agent via
`ModelLoaderService.load()`) has a completely different `__main__` - its own
entry-point script - which never defined `HybridDemandForecaster`. Pickle's
`find_class()` looks up `__main__.HybridDemandForecaster` in the *current*
process and fails:

    AttributeError: Can't get attribute 'HybridDemandForecaster' on
    <module '__main__' from '...test_demand_forecast_agent.py'>

This is not a data or logic bug - it's purely about *where* the class is
defined relative to how the script gets launched.

THE FIX: move the classes here, into a module that is always imported by
its real dotted path (`training_models.hybrid_forecaster`), never executed
directly as `__main__`. `model_training.py` now just imports from here and
drives the fit/evaluate/save pipeline. Pickle stores
`training_models.hybrid_forecaster.HybridDemandForecaster` as the class
reference, and ANY process that has the repo root on `sys.path` (every
entry point in this project already adds it) can resolve that import
automatically at unpickling time - regardless of whether that process
already imported it, and regardless of how model_training.py itself was
invoked.

IMPORTANT: any hybrid_model.pkl trained BEFORE this fix was saved under the
old `__main__` reference and is still broken - you must retrain (rerun
model_training.py) after this fix to get a working pickle. See the
integration guide for the exact steps.

No modeling logic changed vs. your last working run (which hit 94.73% test
accuracy) - this is a pure relocation. Hyperparameters, the log1p target
transform, and the real (non-fake) SARIMAX validate/evaluate path are
carried over unchanged.
"""
import os
import sys

# Defensive: guarantees this module can resolve demand_forecast_agent's
# FeatureEngineeringService even if something imports this file directly
# without having already set up sys.path itself.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)
from sklearn.preprocessing import StandardScaler

from demand_forecast_agent.services.feature_engineering_service import (
    FeatureEngineeringService,
)

try:
    from xgboost import XGBRegressor
except ImportError:  # pragma: no cover - exercised only in envs without xgboost
    XGBRegressor = None

try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
except ImportError:  # pragma: no cover
    SARIMAX = None


class SARIMAXModel:
    """SARIMAX Time Series Model"""

    def __init__(self, order=(1, 1, 1), seasonal_order=(1, 1, 1, 7)):
        self.order = order
        self.seasonal_order = seasonal_order
        self.model = None
        self.results = None

    def fit(self, series, exog=None):
        if SARIMAX is None:
            return False
        try:
            self.model = SARIMAX(
                series,
                exog=exog,
                order=self.order,
                seasonal_order=self.seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            self.results = self.model.fit(disp=False, maxiter=200)
            return True
        except Exception as e:
            print(f"Warning: SARIMAX fit failed: {str(e)}")
            return False

    def forecast(self, steps, exog=None):
        if self.results is None:
            return None
        try:
            forecast = self.results.get_forecast(
                steps=steps, exog=exog if exog is not None else None
            ).predicted_mean
            return forecast if isinstance(forecast, np.ndarray) else forecast.values
        except Exception as e:
            print(f"Warning: SARIMAX forecast failed: {e}")
            return None


class XGBoostModel:
    """XGBoost ML Model.

    Feature list is the single shared, fixed
    FeatureEngineeringService.MODEL_FEATURES - identical at fit and predict
    time, and identical to what the live agent builds at inference.

    Trains on log1p(daily_demand) and inverse-transforms with expm1 at
    predict time (MAPE is a relative-error metric; fitting in log-space
    optimizes something much closer to that than raw-scale error).
    """

    FEATURE_COLS = FeatureEngineeringService.MODEL_FEATURES

    def __init__(self, n_estimators=350, max_depth=7, learning_rate=0.06):
        if XGBRegressor is None:
            raise ImportError(
                "xgboost is required to train the demand forecast model. "
                "Install with: pip install xgboost"
            )
        self.model = XGBRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=3,
            random_state=42,
            n_jobs=-1,
        )
        self.scaler_X = StandardScaler()
        self.feature_cols = list(self.FEATURE_COLS)

    def prepare_features(self, df, target_col="daily_demand"):
        """Reindex onto the fixed feature list (fill_value=0 for anything
        missing) so the matrix shape is identical at fit and predict time."""
        X = df.reindex(columns=self.feature_cols, fill_value=0).fillna(0).values
        y = df[target_col].fillna(0).values if target_col in df.columns else None
        return X, y, self.feature_cols

    def fit(self, df_train):
        X_train, y_train, _ = self.prepare_features(df_train)
        X_train_scaled = self.scaler_X.fit_transform(X_train)
        self.model.fit(X_train_scaled, np.log1p(y_train))
        return self

    def predict(self, df):
        X, _, _ = self.prepare_features(df)
        X_scaled = self.scaler_X.transform(X)
        log_pred = self.model.predict(X_scaled)
        return np.maximum(np.expm1(log_pred), 0)


class HybridDemandForecaster:
    """Ensemble: Combines SARIMAX (60%) + XGBoost (40%)"""

    def __init__(self, sarimax_weight=0.6, xgboost_weight=0.4):
        self.sarimax_weight = sarimax_weight
        self.xgboost_weight = xgboost_weight
        self.sarimax_models = {}  # per product_id
        self.xgboost_model = XGBoostModel()
        self.item_scaler = {}  # per-product scalers
        self.metrics = {}
        # Tracks how many steps-ahead have already been forecasted for each
        # product, so validate() (called first) and evaluate() (called
        # second, on the subsequent block of dates) get genuinely
        # sequential, non-overlapping SARIMAX forecasts.
        self._sarimax_cursor = {}

    def _compute_metrics(self, actuals, preds):
        actuals = np.array(actuals)
        preds = np.array(preds)
        mae = mean_absolute_error(actuals, preds)
        rmse = np.sqrt(mean_squared_error(actuals, preds))
        mape = mean_absolute_percentage_error(np.maximum(actuals, 1), preds)
        r2 = r2_score(actuals, preds)
        mean_actual = max(np.mean(actuals), 1e-6)
        return {
            "MAE_pct": round((mae / mean_actual) * 100, 2),
            "RMSE_pct": round((rmse / mean_actual) * 100, 2),
            "MAPE_pct": round(mape * 100, 2),
            "R2_pct": round(r2 * 100, 2),
            "Accuracy_pct": round(max(0, (1 - mape)) * 100, 2),
        }

    def fit(self, train_df, val_df):
        print("\n" + "=" * 70)
        print("MODEL TRAINING - HYBRID SARIMAX + XGBoost")
        print("=" * 70)

        print("\n[TRAIN] XGBoost Global Model...")
        self.xgboost_model.fit(train_df)
        print("\u2713 XGBoost trained")

        print("\n[TRAIN] Per-Product SARIMAX Models...")
        products = train_df["product_id"].unique()[:20]  # top 20 for speed

        for idx, product in enumerate(products, 1):
            item_data = train_df[train_df["product_id"] == product].sort_values("date")

            if len(item_data) >= 30:
                series = item_data["daily_demand"].values

                scaler = StandardScaler()
                series_scaled = scaler.fit_transform(series.reshape(-1, 1)).flatten()
                self.item_scaler[product] = scaler

                sm = SARIMAXModel()
                if sm.fit(series_scaled):
                    self.sarimax_models[product] = sm
                    print(f"  \u2713 Product {idx:3d}/{len(products)}: {product}")

        print(f"\u2713 Fitted {len(self.sarimax_models)} product-level SARIMAX models")
        print("\n[TRAIN METRICS] Calculating Training Performance...")
        train_preds = self.xgboost_model.predict(train_df)
        train_metrics = self._compute_metrics(train_df["daily_demand"].values, train_preds)
        self.metrics["train"] = train_metrics
        print("\nTraining Metrics:")
        for k, v in train_metrics.items():
            print(f"  {k:<12}: {v:.2f}%")

        self._validate(val_df)
        return self

    def _validate(self, val_df):
        print("\n[VALIDATE] Evaluating on Validation Set...")

        val_df = val_df.copy()
        xgb_preds = self.xgboost_model.predict(val_df)
        val_df["xgb_pred"] = xgb_preds

        all_preds, all_actuals = [], []

        for product in self.sarimax_models.keys():
            item_mask = val_df["product_id"] == product
            if item_mask.sum() > 0:
                item_val = val_df[item_mask].sort_values("date").copy()
                item_val["sarimax_pred"] = self._real_sarimax_forecast(
                    product, steps=len(item_val), fallback=item_val["xgb_pred"].values
                )
                item_val["hybrid_pred"] = (
                    self.sarimax_weight * item_val["sarimax_pred"]
                    + self.xgboost_weight * item_val["xgb_pred"]
                )
                all_preds.extend(item_val["hybrid_pred"].values)
                all_actuals.extend(item_val["daily_demand"].values)

        if len(all_preds) == 0:
            all_preds = xgb_preds
            all_actuals = val_df["daily_demand"].values

        metrics = self._compute_metrics(all_actuals, all_preds)
        self.metrics["val"] = metrics
        print("\nValidation Metrics:")
        for k, v in metrics.items():
            print(f"  {k:<12}: {v:.2f}%")

    def _real_sarimax_forecast(self, product, steps, fallback):
        """Genuine out-of-sample SARIMAX forecast for `product`, inverse-
        scaled back to real units, continuing sequentially from wherever
        this product's forecast cursor last left off. Falls back to the
        XGBoost prediction for that slice if SARIMAX forecasting fails."""
        sm = self.sarimax_models.get(product)
        if sm is None:
            return fallback

        already_consumed = self._sarimax_cursor.get(product, 0)
        total_steps_needed = already_consumed + steps

        raw_forecast = sm.forecast(steps=total_steps_needed)
        if raw_forecast is None or len(raw_forecast) < total_steps_needed:
            return fallback

        this_slice = raw_forecast[already_consumed:total_steps_needed]
        self._sarimax_cursor[product] = total_steps_needed

        scaler = self.item_scaler.get(product)
        if scaler is not None:
            this_slice = scaler.inverse_transform(
                np.asarray(this_slice).reshape(-1, 1)
            ).flatten()
        return np.maximum(this_slice, 0)

    def forecast(self, df, steps_ahead=7, item_id=None):
        """
        Forecast demand.

        Args:
            df: model-input DataFrame - already reindexed onto
                FeatureEngineeringService.MODEL_FEATURES by the caller.
            steps_ahead: forecast horizon.
            item_id: product id (as a string) for SARIMAX lookup. Optional.
        """
        xgb_forecast = self.xgboost_model.predict(df)

        sarimax_forecast = None
        lookup_key = None
        if item_id is not None:
            for candidate in (item_id, str(item_id)):
                if candidate in self.sarimax_models:
                    lookup_key = candidate
                    break
            if lookup_key is None:
                try:
                    numeric_id = int(item_id)
                    if numeric_id in self.sarimax_models:
                        lookup_key = numeric_id
                except (TypeError, ValueError):
                    pass

        if lookup_key is not None:
            sm = self.sarimax_models[lookup_key]
            sarimax_forecast = sm.forecast(steps=steps_ahead)

            if sarimax_forecast is not None and lookup_key in self.item_scaler:
                scaler = self.item_scaler[lookup_key]
                sarimax_forecast = scaler.inverse_transform(
                    sarimax_forecast.reshape(-1, 1)
                ).flatten()

        if sarimax_forecast is not None and len(sarimax_forecast) > 0:
            forecast = (
                self.sarimax_weight * sarimax_forecast[: len(xgb_forecast)]
                + self.xgboost_weight * xgb_forecast
            )
        else:
            forecast = xgb_forecast

        return np.maximum(forecast, 0)

    def evaluate(self, test_df):
        print("\n" + "=" * 70)
        print("MODEL EVALUATION - TEST SET")
        print("=" * 70)

        test_df = test_df.copy()
        xgb_preds = self.xgboost_model.predict(test_df)
        test_df["xgb_pred"] = xgb_preds

        all_preds, all_actuals = [], []
        per_item_results = {}

        for product in test_df["product_id"].unique():
            item_mask = test_df["product_id"] == product
            item_test = test_df[item_mask].sort_values("date").copy()

            item_test["sarimax_pred"] = self._real_sarimax_forecast(
                product, steps=len(item_test), fallback=item_test["xgb_pred"].values
            )

            item_test["hybrid_pred"] = (
                self.sarimax_weight * item_test["sarimax_pred"]
                + self.xgboost_weight * item_test["xgb_pred"]
            )

            y_true = item_test["daily_demand"].values
            y_pred = item_test["hybrid_pred"].values

            item_mae = mean_absolute_error(y_true, y_pred)
            item_rmse = np.sqrt(mean_squared_error(y_true, y_pred))
            item_mape = mean_absolute_percentage_error(y_true, np.maximum(y_pred, 1))
            mean_actual = max(np.mean(y_true), 1)

            per_item_results[product] = {
                "count": len(item_test),
                "MAE_pct": round((item_mae / mean_actual) * 100, 2),
                "RMSE_pct": round((item_rmse / mean_actual) * 100, 2),
                "MAPE_pct": round(item_mape * 100, 2),
            }

            all_preds.extend(y_pred)
            all_actuals.extend(y_true)

        metrics = self._compute_metrics(all_actuals, all_preds)
        self.metrics["test"] = metrics

        print("\nOverall Test Metrics:")
        for k, v in metrics.items():
            print(f"  {k:<12}: {v:.2f}%")

        return {
            "overall": self.metrics["test"],
            "per_item": per_item_results,
            "actuals": all_actuals,
            "predictions": all_preds,
        }

    def save(self, path="hybrid_model.pkl"):
        import joblib

        joblib.dump(self, path)
        print(f"\n\u2713 Model saved to {path}")

    @staticmethod
    def load(path="hybrid_model.pkl"):
        import joblib

        model = joblib.load(path)
        print(f"\u2713 Model loaded from {path}")
        return model
