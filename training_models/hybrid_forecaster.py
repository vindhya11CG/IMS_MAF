"""
SARIMAX + XGBoost Hybrid Demand Forecasting Model - model classes only.

Updated for event-driven demand forecasting with expanded feature set,
segment-level evaluation, and feature importance reporting.
"""
import importlib
import os
import sys

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

XGBRegressor = None
SARIMAX = None


def _load_xgboost():
    global XGBRegressor
    if XGBRegressor is None:
        try:
            xgboost_mod = importlib.import_module("xgboost")
            XGBRegressor = getattr(xgboost_mod, "XGBRegressor")
        except Exception:
            XGBRegressor = None
    return XGBRegressor


def _load_sarimax():
    global SARIMAX
    if SARIMAX is None:
        try:
            sarimax_mod = importlib.import_module("statsmodels.tsa.statespace.sarimax")
            SARIMAX = getattr(sarimax_mod, "SARIMAX")
        except Exception:
            SARIMAX = None
    return SARIMAX


class SARIMAXModel:
    """SARIMAX Time Series Model"""

    def __init__(self, order=(1, 1, 1), seasonal_order=(1, 1, 1, 7)):
        self.order = order
        self.seasonal_order = seasonal_order
        self.model = None
        self.results = None

    def fit(self, series, exog=None):
        sarimax_class = _load_sarimax()
        if sarimax_class is None:
            return False
        try:
            self.model = sarimax_class(
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
    """XGBoost ML Model with expanded event-driven feature set."""

    FEATURE_COLS = FeatureEngineeringService.MODEL_FEATURES

    def __init__(self, n_estimators=500, max_depth=8, learning_rate=0.05):
        xgb_class = _load_xgboost()
        if xgb_class is None:
            raise ImportError(
                "xgboost is required. Install with: pip install xgboost"
            )
        self.model = xgb_class(
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
        """Reindex onto the fixed feature list so the matrix shape is identical
        at fit and predict time."""
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

    def feature_importances(self, top_n=20):
        """Return (feature_name, importance) pairs sorted descending."""
        importances = self.model.feature_importances_
        pairs = list(zip(self.feature_cols, importances))
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[:top_n]


class HybridDemandForecaster:
    """Ensemble: Combines SARIMAX (60%) + XGBoost (40%)"""

    def __init__(self, sarimax_weight=0.6, xgboost_weight=0.4):
        self.sarimax_weight = sarimax_weight
        self.xgboost_weight = xgboost_weight
        self.sarimax_models = {}
        self.xgboost_model = XGBoostModel()
        self.item_scaler = {}
        self.metrics = {}
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

    def _compute_segment_metrics(self, df, pred_col="xgb_pred"):
        """Compute metrics for event-specific subsets."""
        segments = {}

        # Festival days
        fest_mask = df.get("is_festival_day_int", df.get("is_festival_day", pd.Series(dtype=float))).astype(float) == 1
        if fest_mask.sum() > 10:
            segments["festival"] = self._compute_metrics(
                df.loc[fest_mask, "daily_demand"].values,
                df.loc[fest_mask, pred_col].values,
            )

        # Extreme weather
        wx_mask = df.get("extreme_weather_flag_int", df.get("extreme_weather_flag", pd.Series(dtype=float))).astype(float) == 1
        if wx_mask.sum() > 10:
            segments["extreme_weather"] = self._compute_metrics(
                df.loc[wx_mask, "daily_demand"].values,
                df.loc[wx_mask, pred_col].values,
            )

        # Weekends
        wknd_mask = df.get("is_weekend", pd.Series(dtype=float)).astype(float) == 1
        if wknd_mask.sum() > 10:
            segments["weekend"] = self._compute_metrics(
                df.loc[wknd_mask, "daily_demand"].values,
                df.loc[wknd_mask, pred_col].values,
            )

        # Regular weekdays (no event)
        regular_mask = (~fest_mask) & (~wx_mask) & (~wknd_mask)
        if regular_mask.sum() > 10:
            segments["regular_weekday"] = self._compute_metrics(
                df.loc[regular_mask, "daily_demand"].values,
                df.loc[regular_mask, pred_col].values,
            )

        return segments

    def fit(self, train_df, val_df):
        print("\n" + "=" * 70)
        print("MODEL TRAINING - HYBRID SARIMAX + XGBoost")
        print("=" * 70)

        self._sarimax_cursor = {}
        print("\n[TRAIN] XGBoost Global Model...")
        self.xgboost_model.fit(train_df)
        print("[OK] XGBoost trained")

        # Feature importance
        print("\n[IMPORTANCE] Top 20 XGBoost Feature Importances:")
        importances = self.xgboost_model.feature_importances(top_n=20)
        for name, imp in importances:
            print(f"  {name:<35} {imp:.4f}")

        print("\n[TRAIN] Per-Product SARIMAX Models...")
        products = train_df["product_id"].unique()[:20]

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
                    print(f"  [OK] Product {idx:3d}/{len(products)}: {product}")

        print(f"[OK] Fitted {len(self.sarimax_models)} product-level SARIMAX models")

        # Training metrics
        print("\n[TRAIN METRICS]")
        train_preds = self.xgboost_model.predict(train_df)
        train_metrics = self._compute_metrics(train_df["daily_demand"].values, train_preds)
        self.metrics["train"] = train_metrics
        for k, v in train_metrics.items():
            print(f"  {k:<12}: {v:.2f}%")

        self._validate(val_df)
        return self

    def _validate(self, val_df):
        print("\n[VALIDATE] Evaluating on Validation Set...")
        self._sarimax_cursor = {}

        val_df = val_df.copy()
        xgb_preds = self.xgboost_model.predict(val_df)
        val_df["xgb_pred"] = xgb_preds

        all_preds, all_actuals = [], []

        for product in val_df["product_id"].unique():
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

        # Segment metrics
        segment_metrics = self._compute_segment_metrics(val_df, "xgb_pred")
        self.metrics["val_segments"] = segment_metrics
        if segment_metrics:
            print("\nValidation Segment Metrics:")
            for seg_name, seg_m in segment_metrics.items():
                print(f"  [{seg_name}] Accuracy={seg_m['Accuracy_pct']:.1f}%, MAPE={seg_m['MAPE_pct']:.1f}%")

    def _real_sarimax_forecast(self, product, steps, fallback):
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

        if sarimax_forecast is not None and len(sarimax_forecast) >= len(xgb_forecast):
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

        self._sarimax_cursor = {}

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

        # Segment metrics on test set
        segment_metrics = self._compute_segment_metrics(test_df, "xgb_pred")
        self.metrics["test_segments"] = segment_metrics
        if segment_metrics:
            print("\nTest Segment Metrics:")
            for seg_name, seg_m in segment_metrics.items():
                print(f"  [{seg_name}] Accuracy={seg_m['Accuracy_pct']:.1f}%, MAPE={seg_m['MAPE_pct']:.1f}%")

        return {
            "overall": self.metrics["test"],
            "segments": segment_metrics,
            "per_item": per_item_results,
            "actuals": all_actuals,
            "predictions": all_preds,
        }

    def save(self, path="hybrid_model.pkl"):
        import joblib

        joblib.dump(self, path)
        print(f"\n[OK] Model saved to {path}")

    @staticmethod
    def load(path="hybrid_model.pkl"):
        import joblib

        model = joblib.load(path)
        print(f"[OK] Model loaded from {path}")
        return model
