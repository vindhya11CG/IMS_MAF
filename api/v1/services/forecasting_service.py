"""Forecasting service — thin orchestration layer around the existing
``demand_forecast_agent`` services.

Responsibilities
----------------
* Load and cache ``model_features.json`` and ``model_metrics.json`` once.
* Expose ``predict_single``, ``predict_batch``, ``generate_forecast``,
  ``reorder_recommendation``, ``risk_assessment``, and ``simulate`` methods.
* Keep business logic here so router controllers stay thin.
* Reuse ``ModelLoaderService``, ``ForecastService``, ``BatchForecastService``,
  ``FeatureEngineeringService``, ``InventoryDecisionService``, and
  ``ReorderService`` from ``demand_forecast_agent``.
* Never reload JSON artifacts or the model pickle on individual requests.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Artifact paths (relative to project CWD — same convention as ModelLoaderService)
# ---------------------------------------------------------------------------
_FEATURES_PATH = Path("training_models/model_features.json")
_METRICS_PATH = Path("training_models/model_metrics.json")

# Training dataset constants (from the spec — do NOT recompute per request)
_DATASET_ROWS = 721_080
_NUM_PRODUCTS = 2_000
_NUM_LOCATIONS = 53
_NUM_CATEGORIES = 8
_TRAINING_DATE_START = "2025-01-01"
_TRAINING_DATE_END = "2025-04-30"
_MODEL_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# ForecastingService
# ---------------------------------------------------------------------------


class ForecastingService:
    """Thread-safe singleton service for all demand-forecasting API operations.

    All heavy objects (model, JSON artifacts) are initialised lazily on the
    first call and then reused for the lifetime of the process.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Cached JSON artifacts
        self._features_data: Optional[Dict[str, Any]] = None
        self._metrics_data: Optional[Dict[str, Any]] = None

        # Lazy-imported agent services (avoid paying import cost until needed)
        self._forecast_service = None
        self._batch_service = None
        self._engineer = None
        self._decision_service = None
        self._reorder_service = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_features_data(self) -> Dict[str, Any]:
        """Return cached ``model_features.json`` content."""
        if self._features_data is None:
            with self._lock:
                if self._features_data is None:
                    try:
                        with _FEATURES_PATH.open("r", encoding="utf-8") as fh:
                            self._features_data = json.load(fh)
                        logger.info("Loaded model_features.json from %s", _FEATURES_PATH)
                    except Exception as exc:
                        logger.error("Cannot read model_features.json: %s", exc)
                        self._features_data = {}
        return self._features_data

    def _get_metrics_data(self) -> Dict[str, Any]:
        """Return cached ``model_metrics.json`` content."""
        if self._metrics_data is None:
            with self._lock:
                if self._metrics_data is None:
                    try:
                        with _METRICS_PATH.open("r", encoding="utf-8") as fh:
                            self._metrics_data = json.load(fh)
                        logger.info("Loaded model_metrics.json from %s", _METRICS_PATH)
                    except Exception as exc:
                        logger.error("Cannot read model_metrics.json: %s", exc)
                        self._metrics_data = {}
        return self._metrics_data

    def _get_forecast_service(self):
        """Lazily create and cache a ``ForecastService`` instance."""
        if self._forecast_service is None:
            with self._lock:
                if self._forecast_service is None:
                    from demand_forecast_agent.services.core_forecasting_service import (
                        ForecastService,
                    )
                    self._forecast_service = ForecastService()
        return self._forecast_service

    def _get_batch_service(self):
        """Lazily create and cache a ``BatchForecastService`` instance (XGBoost-only path)."""
        if self._batch_service is None:
            with self._lock:
                if self._batch_service is None:
                    from demand_forecast_agent.services.core_forecasting_service import (
                        BatchForecastService,
                    )
                    self._batch_service = BatchForecastService()
        return self._batch_service

    def _get_engineer(self):
        """Lazily create and cache a ``FeatureEngineeringService`` instance."""
        if self._engineer is None:
            with self._lock:
                if self._engineer is None:
                    from demand_forecast_agent.services.feature_engineering_service import (
                        FeatureEngineeringService,
                    )
                    self._engineer = FeatureEngineeringService()
        return self._engineer

    def _get_decision_service(self):
        if self._decision_service is None:
            with self._lock:
                if self._decision_service is None:
                    from demand_forecast_agent.services.decision_services import (
                        InventoryDecisionService,
                    )
                    self._decision_service = InventoryDecisionService()
        return self._decision_service

    def _get_reorder_service(self):
        if self._reorder_service is None:
            with self._lock:
                if self._reorder_service is None:
                    from demand_forecast_agent.services.decision_services import ReorderService
                    self._reorder_service = ReorderService()
        return self._reorder_service

    def _get_model(self):
        """Return the already-loaded HybridDemandForecaster singleton."""
        from demand_forecast_agent.services.core_forecasting_service import ModelLoaderService
        return ModelLoaderService.load()

    def _base_confidence(self) -> float:
        """Return test accuracy from metrics JSON as baseline confidence score."""
        metrics = self._get_metrics_data()
        return round(metrics.get("test_metrics", {}).get("Accuracy_pct", 90.0), 2)

    def _build_inference_payload(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise an incoming request dict into the shape FeatureEngineeringService expects."""
        return {
            "product_id": item.get("product_id", 0),
            "location_id": item.get("location_id", 0),
            "on_hand_qty": item.get("on_hand_qty", 0),
            "allocated_qty": item.get("allocated_qty", 0),
            "safety_stock_qty": item.get("safety_stock_qty", 0),
            "reorder_point_qty": item.get("reorder_point_qty", 0),
            "date": item.get("date"),
            "is_promotional": item.get("is_promotional", False),
            "annual_units_max": item.get("annual_units_max", 0),
            "avg_retail_price": item.get("avg_retail_price", 0.0),
            "holding_cost_per_unit_day": item.get("holding_cost_per_unit_day", 0.0),
            "handling_cost_per_unit": item.get("handling_cost_per_unit", 0.0),
            "order_fulfillment_rate": item.get("order_fulfillment_rate", 0.0),
            "total_orders_last_month": item.get("total_orders_last_month", 0),
            "turnover_ratio": item.get("turnover_ratio", 0.0),
            "demand_std_dev": item.get("demand_std_dev", 0.0),
            "lead_time_days": item.get("lead_time_days", 0),
            "season_multiplier": item.get("season_multiplier", 1.0),
            "category_id": item.get("category_id", 0),
            "velocity_class_id": item.get("velocity_class_id", 0),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_model_info(self) -> Dict[str, Any]:
        """Return model metadata from ``model_features.json``."""
        features_data = self._get_features_data()
        return {
            "model_name": features_data.get("model_name", "Hybrid SARIMAX + XGBoost"),
            "algorithm": "Hybrid SARIMAX + XGBoost ensemble",
            "training_date": features_data.get("created_at", "Unknown"),
            "num_products": _NUM_PRODUCTS,
            "num_locations": _NUM_LOCATIONS,
            "num_categories": _NUM_CATEGORIES,
            "dataset_size": _DATASET_ROWS,
            "training_date_range": {
                "start": _TRAINING_DATE_START,
                "end": _TRAINING_DATE_END,
            },
            "version": _MODEL_VERSION,
            "artifact_paths": {
                "model": str(_FEATURES_PATH.parent / "hybrid_model.pkl"),
                "metrics": str(_METRICS_PATH),
                "features": str(_FEATURES_PATH),
            },
            "sarimax_weight": features_data.get("sarimax_weight", 0.6),
            "xgboost_weight": features_data.get("xgboost_weight", 0.4),
            "num_sarimax_models": features_data.get("num_sarimax_models", 20),
            "feature_count": features_data.get("feature_count", 25),
        }

    def get_model_metrics(self) -> Dict[str, Any]:
        """Return raw metrics from ``model_metrics.json`` with human-friendly field names."""
        raw = self._get_metrics_data()

        def _format(section: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "accuracy_pct": section.get("Accuracy_pct"),
                "mape_pct": section.get("MAPE_pct"),
                "mae_pct": section.get("MAE_pct"),
                "rmse_pct": section.get("RMSE_pct"),
                "r2_pct": section.get("R2_pct"),
            }

        return {
            "train_metrics": _format(raw.get("train_metrics", {})),
            "val_metrics": _format(raw.get("val_metrics", {})),
            "test_metrics": _format(raw.get("test_metrics", {})),
        }

    def get_feature_list(self) -> Dict[str, Any]:
        """Return the model feature manifest."""
        features_data = self._get_features_data()
        xgb_features: List[str] = features_data.get("xgboost_features", [])

        categorical = ["category_id", "velocity_class_id", "is_promotional_int"]
        numerical = [f for f in xgb_features if f not in categorical]

        return {
            "feature_names": xgb_features,
            "categorical_features": [f for f in categorical if f in xgb_features],
            "numerical_features": numerical,
            "target_column": "demand",
            "feature_count": len(xgb_features),
        }

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_single(
        self, payload: Dict[str, Any], horizon: int = 14
    ) -> Dict[str, Any]:
        """Run a single-row hybrid (SARIMAX + XGBoost) prediction.

        Args:
            payload: Raw request dict containing inventory features.
            horizon:  Forecast horizon in days.

        Returns:
            Dict with ``predicted_demand``, ``confidence``,
            ``prediction_interval``, ``model_used``, and ``latency_ms``.
        """
        t0 = time.perf_counter()
        engineer = self._get_engineer()
        forecast_service = self._get_forecast_service()

        normalised = self._build_inference_payload(payload)
        engineered_df = engineer.execute(normalised)

        result = forecast_service.execute(
            engineered_df,
            horizon=horizon,
            product_id=payload.get("product_id", 0),
        )

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        if result["status"] != "SUCCESS":
            raise RuntimeError(result.get("message", "Forecast failed."))

        predicted = round(result["forecast"], 2)
        confidence = self._base_confidence()
        margin = round(predicted * (1 - confidence / 100) * 1.96, 2)

        return {
            "predicted_demand": predicted,
            "confidence_score": confidence,
            "prediction_interval": {
                "lower": max(0.0, round(predicted - margin, 2)),
                "upper": round(predicted + margin, 2),
            },
            "model_used": "Hybrid SARIMAX+XGBoost",
            "horizon_days": horizon,
            "latency_ms": latency_ms,
        }

    def predict_batch(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Vectorized batch prediction (XGBoost-only, fast path).

        Args:
            rows: List of raw request dicts.

        Returns:
            List of prediction dicts in the same order as ``rows``.
        """
        t0 = time.perf_counter()
        engineer = self._get_engineer()
        batch_service = self._get_batch_service()
        model = self._get_model()
        features_data = self._get_features_data()
        feature_names: List[str] = features_data.get(
            "xgboost_features", engineer.MODEL_FEATURES
        )

        normalised_rows = [self._build_inference_payload(r) for r in rows]
        predictions = batch_service.execute(model, normalised_rows, feature_names, engineer)

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        confidence = self._base_confidence()
        per_item_latency = round(latency_ms / max(len(rows), 1), 2)

        results: List[Dict[str, Any]] = []
        for i, (row, pred) in enumerate(zip(rows, predictions)):
            margin = round(pred * (1 - confidence / 100) * 1.96, 2)
            results.append(
                {
                    "index": i,
                    "product_id": row.get("product_id"),
                    "location_id": row.get("location_id"),
                    "predicted_demand": pred,
                    "confidence_score": confidence,
                    "prediction_interval": {
                        "lower": max(0.0, round(pred - margin, 2)),
                        "upper": round(pred + margin, 2),
                    },
                    "model_used": "XGBoost (batch-vectorized)",
                    "latency_ms": per_item_latency,
                }
            )

        logger.info(
            "Batch predict: %d rows in %.1f ms (%.2f ms/row)",
            len(rows),
            latency_ms,
            per_item_latency,
        )
        return results

    def generate_forecast(
        self,
        product_id: int,
        location_id: int,
        days: int,
        base_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate a rolling N-day demand forecast for a product at a location.

        Each day is predicted independently with a date offset applied to the
        temporal features in ``FeatureEngineeringService``.

        Args:
            product_id:   Product SKU identifier.
            location_id:  Location identifier.
            days:         Number of forecast days (1–365).
            base_payload: Inventory context dict (on_hand_qty, safety_stock, etc.).

        Returns:
            List of daily forecast dicts with ``date``, ``forecasted_demand``,
            ``confidence``, ``trend``, and ``seasonality`` fields.
        """
        engineer = self._get_engineer()
        forecast_service = self._get_forecast_service()
        confidence = self._base_confidence()

        forecast_days: List[Dict[str, Any]] = []
        base_date = datetime.now().date()
        prev_demand: Optional[float] = None

        for offset in range(days):
            current_date = base_date + timedelta(days=offset)

            payload = {**self._build_inference_payload(base_payload)}
            payload["product_id"] = product_id
            payload["location_id"] = location_id
            payload["date"] = str(current_date)

            engineered_df = engineer.execute(payload)
            result = forecast_service.execute(
                engineered_df,
                horizon=1,
                product_id=product_id,
            )

            if result["status"] != "SUCCESS":
                logger.warning(
                    "Forecast failed for product %s on %s: %s",
                    product_id,
                    current_date,
                    result.get("message"),
                )
                continue

            pred = round(result["forecast"], 2)
            margin = round(pred * (1 - confidence / 100) * 1.96, 2)

            # Trend detection vs previous day
            if prev_demand is None:
                trend = "STABLE"
            elif pred > prev_demand * 1.05:
                trend = "INCREASING"
            elif pred < prev_demand * 0.95:
                trend = "DECREASING"
            else:
                trend = "STABLE"

            # Simple seasonality tag based on month
            month = current_date.month
            if month in (11, 12, 1):
                seasonality = "HIGH"
            elif month in (6, 7, 8):
                seasonality = "MEDIUM"
            else:
                seasonality = "NORMAL"

            forecast_days.append(
                {
                    "date": str(current_date),
                    "forecasted_demand": pred,
                    "confidence": confidence,
                    "prediction_interval": {
                        "lower": max(0.0, round(pred - margin, 2)),
                        "upper": round(pred + margin, 2),
                    },
                    "trend": trend,
                    "seasonality": seasonality,
                }
            )
            prev_demand = pred

        return forecast_days

    # ------------------------------------------------------------------
    # Inventory helpers
    # ------------------------------------------------------------------

    def reorder_recommendation(
        self,
        on_hand_qty: int,
        allocated_qty: int,
        in_transit_qty: int,
        safety_stock_qty: int,
        reorder_point_qty: int,
        lead_time_days: int,
        forecasted_demand: Optional[float],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute a reorder recommendation.

        If ``forecasted_demand`` is ``None``, runs the forecasting model first.

        Returns:
            Dict with ``recommended_reorder_qty``, ``days_until_stockout``,
            ``reorder_urgency``, and ``confidence``.
        """
        if forecasted_demand is None:
            result = self.predict_single(payload, horizon=lead_time_days or 14)
            forecasted_demand = result["predicted_demand"]

        decision_service = self._get_decision_service()
        reorder_service = self._get_reorder_service()

        available = on_hand_qty - allocated_qty + in_transit_qty
        projected = on_hand_qty + in_transit_qty - forecasted_demand

        decision = decision_service.execute(
            forecasted_demand, on_hand_qty, reorder_point_qty, safety_stock_qty
        )
        reorder_qty = reorder_service.execute(
            forecasted_demand,
            on_hand_qty,
            allocated_qty,
            safety_stock_qty,
            transit=in_transit_qty,
        )

        # Days until stockout = available stock / daily demand rate
        daily_demand = forecasted_demand / max(lead_time_days or 14, 1)
        days_until_stockout = (
            math.floor(available / daily_demand) if daily_demand > 0 else 999
        )

        urgency_map = {"HIGH": "CRITICAL", "MEDIUM": "MODERATE", "LOW": "LOW"}
        urgency = urgency_map.get(decision["severity"], "LOW")

        return {
            "recommended_reorder_qty": reorder_qty,
            "days_until_stockout": days_until_stockout,
            "reorder_urgency": urgency,
            "decision": decision["decision"],
            "forecasted_demand": round(forecasted_demand, 2),
            "available_stock": available,
            "projected_stock_after_lead_time": round(projected, 2),
            "confidence": self._base_confidence(),
        }

    def risk_assessment(
        self,
        current_stock: int,
        safety_stock_qty: int,
        reorder_point_qty: int,
        forecasted_demand: Optional[float],
        lead_time_days: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """ML-based inventory risk classification.

        Classification logic
        --------------------
        - CRITICAL : projected stock ≤ 0
        - HIGH     : projected stock ≤ safety_stock
        - MEDIUM   : projected stock ≤ reorder_point
        - LOW      : otherwise

        Returns:
            Dict with ``risk_level``, ``risk_score``, ``reason_codes``,
            and ``recommended_action``.
        """
        if forecasted_demand is None:
            result = self.predict_single(payload, horizon=lead_time_days or 14)
            forecasted_demand = result["predicted_demand"]

        projected = current_stock - forecasted_demand
        reason_codes: List[str] = []

        if projected <= 0:
            risk_level = "CRITICAL"
            risk_score = 100.0
            reason_codes.append("STOCKOUT_IMMINENT")
        elif projected <= safety_stock_qty:
            risk_level = "HIGH"
            risk_score = round(75.0 + 25.0 * (1 - projected / max(safety_stock_qty, 1)), 2)
            reason_codes.append("BELOW_SAFETY_STOCK")
        elif projected <= reorder_point_qty:
            risk_level = "MEDIUM"
            risk_score = round(40.0 + 35.0 * (1 - projected / max(reorder_point_qty, 1)), 2)
            reason_codes.append("BELOW_REORDER_POINT")
        else:
            risk_level = "LOW"
            risk_score = round(
                max(0.0, 40.0 * (reorder_point_qty / max(projected, 1))), 2
            )

        if forecasted_demand > current_stock:
            reason_codes.append("DEMAND_EXCEEDS_STOCK")
        if lead_time_days > 0 and projected < forecasted_demand * (lead_time_days / 14):
            reason_codes.append("INSUFFICIENT_COVER_FOR_LEAD_TIME")

        action_map = {
            "CRITICAL": "Place emergency replenishment order immediately.",
            "HIGH": "Expedite pending orders and review safety stock policy.",
            "MEDIUM": "Monitor closely and prepare a purchase order.",
            "LOW": "No immediate action required; monitor stock levels.",
        }

        return {
            "risk_level": risk_level,
            "risk_score": risk_score,
            "reason_codes": reason_codes if reason_codes else ["ADEQUATE_STOCK"],
            "recommended_action": action_map[risk_level],
            "forecasted_demand": round(forecasted_demand, 2),
            "projected_stock": round(projected, 2),
            "confidence": self._base_confidence(),
        }

    def simulate(
        self,
        payload: Dict[str, Any],
        scenario: Dict[str, Any],
        horizon: int = 14,
    ) -> Dict[str, Any]:
        """What-if simulation against a set of scenario overrides.

        Scenario keys (all optional)
        ------------------------------
        ``demand_multiplier``  – scale forecasted demand (e.g. 1.3 = +30 %)
        ``is_promotional``     – flag as promotional period
        ``lead_time_days``     – override lead time
        ``price_change_pct``   – percentage change in avg_retail_price
        ``safety_stock_change``– absolute change to safety_stock_qty

        Returns:
            Dict with ``original``, ``simulated``, ``delta``,
            ``business_impact``, and ``recommendation``.
        """
        # --- Baseline prediction ---
        baseline_result = self.predict_single(payload, horizon=horizon)
        baseline_demand = baseline_result["predicted_demand"]

        # --- Build scenario payload ---
        scenario_payload = {**payload}

        demand_multiplier = float(scenario.get("demand_multiplier", 1.0))
        if scenario.get("is_promotional") is not None:
            scenario_payload["is_promotional"] = scenario["is_promotional"]
        if scenario.get("lead_time_days") is not None:
            scenario_payload["lead_time_days"] = int(scenario["lead_time_days"])
        if scenario.get("price_change_pct") is not None:
            pct = float(scenario["price_change_pct"])
            orig_price = float(payload.get("avg_retail_price", 0.0))
            scenario_payload["avg_retail_price"] = round(orig_price * (1 + pct / 100), 4)
        if scenario.get("safety_stock_change") is not None:
            scenario_payload["safety_stock_qty"] = max(
                0,
                int(payload.get("safety_stock_qty", 0))
                + int(scenario["safety_stock_change"]),
            )

        simulated_result = self.predict_single(scenario_payload, horizon=horizon)
        simulated_demand = round(
            simulated_result["predicted_demand"] * demand_multiplier, 2
        )

        delta = round(simulated_demand - baseline_demand, 2)
        delta_pct = round((delta / baseline_demand * 100) if baseline_demand else 0.0, 2)

        # Business impact: rough cost estimate using avg_retail_price
        unit_price = float(payload.get("avg_retail_price", 0.0))
        revenue_impact = round(delta * unit_price, 2)

        if abs(delta_pct) < 5:
            recommendation = "No significant impact expected. Maintain current stock levels."
        elif delta_pct >= 5:
            recommendation = (
                f"Demand is projected to increase by {delta_pct:.1f}%. "
                "Increase safety stock or expedite replenishment."
            )
        else:
            recommendation = (
                f"Demand is projected to decrease by {abs(delta_pct):.1f}%. "
                "Consider reducing open purchase orders to avoid overstock."
            )

        return {
            "original": {
                "predicted_demand": baseline_demand,
                "confidence": baseline_result["confidence_score"],
                "prediction_interval": baseline_result["prediction_interval"],
            },
            "simulated": {
                "predicted_demand": simulated_demand,
                "confidence": simulated_result["confidence_score"],
                "applied_demand_multiplier": demand_multiplier,
            },
            "delta": {
                "absolute": delta,
                "percentage": delta_pct,
            },
            "business_impact": {
                "revenue_impact_estimate": revenue_impact,
                "currency": "USD",
            },
            "recommendation": recommendation,
            "scenario_applied": scenario,
        }


# ---------------------------------------------------------------------------
# Singleton + FastAPI dependency
# ---------------------------------------------------------------------------

_service_instance: Optional[ForecastingService] = None
_instance_lock = threading.Lock()


def get_forecasting_service() -> ForecastingService:
    """Return the global :class:`ForecastingService` singleton.

    Thread-safe lazy initialisation — only one instance is ever created
    regardless of concurrent requests.
    """
    global _service_instance  # noqa: PLW0603
    if _service_instance is None:
        with _instance_lock:
            if _service_instance is None:
                _service_instance = ForecastingService()
                logger.info("ForecastingService singleton initialised.")
    return _service_instance
