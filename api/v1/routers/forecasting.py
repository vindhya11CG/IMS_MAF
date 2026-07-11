"""Demand Forecasting API router.

All 10 endpoints are implemented here as thin controllers.
Business logic lives entirely in :class:`ForecastingService`.

Mount prefix: ``/api/v1/forecasting``
Tag group:    ``Demand Forecasting``
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import JSONResponse

from api.core.dependencies import get_app_state, get_forecast_service
from api.core.state import AppState
from api.v1.schemas.forecasting import (
    ApiResponse,
    BatchPredictData,
    BatchPredictItem,
    BatchPredictRequest,
    BatchPredictResultItem,
    DeltaInfo,
    DemandPoint,
    BusinessImpact,
    ErrorResponse,
    FeatureListData,
    ForecastData,
    ForecastDayResult,
    ForecastRequest,
    HealthData,
    ModelInfoData,
    ModelMetricsData,
    MetricsSection,
    PredictData,
    PredictRequest,
    PredictionInterval,
    ReorderData,
    ReorderRequest,
    ResponseMetadata,
    RiskData,
    RiskRequest,
    SimulateData,
    SimulateRequest,
    TrainingDateRange,
    ArtifactPaths,
)
from api.v1.services.forecasting_service import ForecastingService

logger = logging.getLogger(__name__)

router = APIRouter()

_API_VERSION = "1.0.0"
_TAG = "Demand Forecasting"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _metadata(start_time: float) -> ResponseMetadata:
    return ResponseMetadata(
        timestamp=_now_iso(),
        latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
    )


def _error_response(message: str, errors: List[str], status_code: int = 500) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(message=message, errors=errors).model_dump(),
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    summary="Application health check",
    description=(
        "Returns the current health status of the API, including whether the "
        "forecasting model is loaded into memory, the API version, and uptime."
    ),
    tags=[_TAG],
    responses={
        200: {"description": "API is healthy."},
        503: {"description": "Model not loaded — service degraded."},
    },
)
async def health_check(
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    t0 = time.perf_counter()

    uptime = (datetime.now() - state.startup_time).total_seconds()
    api_status = "healthy" if state.model_loaded else "degraded"

    data = HealthData(
        api_status=api_status,
        model_loaded=state.model_loaded,
        model_loaded_at=(
            state.model_loaded_at.isoformat() if state.model_loaded_at else None
        ),
        version=_API_VERSION,
        uptime_seconds=round(uptime, 2),
    )

    response = ApiResponse[HealthData](
        success=True,
        message="API is running.",
        data=data,
        metadata=_metadata(t0),
    )

    http_status = status.HTTP_200_OK if state.model_loaded else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=http_status, content=response.model_dump())


# ---------------------------------------------------------------------------
# GET /model/info
# ---------------------------------------------------------------------------


@router.get(
    "/model/info",
    summary="Forecasting model metadata",
    description=(
        "Returns static metadata about the deployed Hybrid SARIMAX + XGBoost "
        "forecasting model: training dataset size, number of products and locations, "
        "artifact file paths, and ensemble weights."
    ),
    tags=[_TAG],
)
async def get_model_info(
    svc: ForecastingService = Depends(get_forecast_service),
) -> JSONResponse:
    t0 = time.perf_counter()
    try:
        raw = svc.get_model_info()
        data = ModelInfoData(
            model_name=raw["model_name"],
            algorithm=raw["algorithm"],
            training_date=raw["training_date"],
            num_products=raw["num_products"],
            num_locations=raw["num_locations"],
            num_categories=raw["num_categories"],
            dataset_size=raw["dataset_size"],
            training_date_range=TrainingDateRange(**raw["training_date_range"]),
            version=raw["version"],
            artifact_paths=ArtifactPaths(**raw["artifact_paths"]),
            sarimax_weight=raw["sarimax_weight"],
            xgboost_weight=raw["xgboost_weight"],
            num_sarimax_models=raw["num_sarimax_models"],
            feature_count=raw["feature_count"],
        )
        response = ApiResponse[ModelInfoData](
            success=True,
            message="Model information retrieved successfully.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())
    except Exception as exc:
        logger.exception("Failed to retrieve model info: %s", exc)
        return _error_response("Failed to retrieve model information.", [str(exc)])


# ---------------------------------------------------------------------------
# GET /model/metrics
# ---------------------------------------------------------------------------


@router.get(
    "/model/metrics",
    summary="Forecasting model performance metrics",
    description=(
        "Returns train, validation, and test metrics for the hybrid forecasting "
        "model loaded from ``model_metrics.json``.  Metrics include Accuracy, "
        "MAPE, MAE, RMSE, and R²."
    ),
    tags=[_TAG],
)
async def get_model_metrics(
    svc: ForecastingService = Depends(get_forecast_service),
) -> JSONResponse:
    t0 = time.perf_counter()
    try:
        raw = svc.get_model_metrics()
        data = ModelMetricsData(
            train_metrics=MetricsSection(**raw["train_metrics"]),
            val_metrics=MetricsSection(**raw["val_metrics"]),
            test_metrics=MetricsSection(**raw["test_metrics"]),
        )
        response = ApiResponse[ModelMetricsData](
            success=True,
            message="Model metrics retrieved successfully.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())
    except Exception as exc:
        logger.exception("Failed to retrieve model metrics: %s", exc)
        return _error_response("Failed to retrieve model metrics.", [str(exc)])


# ---------------------------------------------------------------------------
# GET /features
# ---------------------------------------------------------------------------


@router.get(
    "/features",
    summary="Model feature list",
    description=(
        "Returns the complete ordered list of features the forecasting model "
        "expects at inference time, split into categorical and numerical groups, "
        "together with the target column name."
    ),
    tags=[_TAG],
)
async def get_features(
    svc: ForecastingService = Depends(get_forecast_service),
) -> JSONResponse:
    t0 = time.perf_counter()
    try:
        raw = svc.get_feature_list()
        data = FeatureListData(**raw)
        response = ApiResponse[FeatureListData](
            success=True,
            message="Feature list retrieved successfully.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())
    except Exception as exc:
        logger.exception("Failed to retrieve feature list: %s", exc)
        return _error_response("Failed to retrieve feature list.", [str(exc)])


# ---------------------------------------------------------------------------
# POST /predict
# ---------------------------------------------------------------------------


@router.post(
    "/predict",
    summary="Single demand prediction",
    description=(
        "Runs the Hybrid SARIMAX + XGBoost model on a single inventory position "
        "and returns the predicted demand, a confidence score, and a 95 % "
        "prediction interval.\n\n"
        "The model is loaded once at startup; no disk I/O occurs per request."
    ),
    tags=[_TAG],
    responses={
        200: {"description": "Prediction successful."},
        422: {"description": "Validation error — missing or invalid fields."},
        500: {"description": "Model inference failed."},
    },
)
async def predict_single(
    request: PredictRequest,
    svc: ForecastingService = Depends(get_forecast_service),
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    t0 = time.perf_counter()

    if not state.model_loaded:
        return _error_response(
            "Forecasting model is not loaded.",
            ["Model failed to load during startup."],
            status_code=503,
        )

    try:
        payload = request.model_dump()
        horizon = payload.pop("horizon_days", 14)
        result = svc.predict_single(payload, horizon=horizon)

        data = PredictData(
            product_id=request.product_id,
            location_id=request.location_id,
            predicted_demand=result["predicted_demand"],
            confidence_score=result["confidence_score"],
            prediction_interval=PredictionInterval(**result["prediction_interval"]),
            model_used=result["model_used"],
            horizon_days=result["horizon_days"],
            latency_ms=result["latency_ms"],
        )
        response = ApiResponse[PredictData](
            success=True,
            message="Prediction completed successfully.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())

    except RuntimeError as exc:
        logger.warning("Prediction failed for product %s: %s", request.product_id, exc)
        return _error_response("Prediction failed.", [str(exc)], status_code=500)
    except Exception as exc:
        logger.exception("Unexpected error in /predict: %s", exc)
        return _error_response("Internal server error.", [str(exc)], status_code=500)


# ---------------------------------------------------------------------------
# POST /predict/batch
# ---------------------------------------------------------------------------


@router.post(
    "/predict/batch",
    summary="Vectorized batch demand prediction",
    description=(
        "Accepts a list of inventory items (up to 5,000 per request) and "
        "returns predictions for all of them in a single vectorized XGBoost "
        "inference pass — no per-row overhead.\n\n"
        "This endpoint uses the XGBoost component of the hybrid model only, "
        "which makes it much faster than calling ``/predict`` in a loop."
    ),
    tags=[_TAG],
    responses={
        200: {"description": "Batch prediction successful."},
        422: {"description": "Validation error."},
        503: {"description": "Model not loaded."},
    },
)
async def predict_batch(
    request: BatchPredictRequest,
    svc: ForecastingService = Depends(get_forecast_service),
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    t0 = time.perf_counter()

    if not state.model_loaded:
        return _error_response(
            "Forecasting model is not loaded.",
            ["Model failed to load during startup."],
            status_code=503,
        )

    try:
        rows = [item.model_dump() for item in request.items]
        predictions = svc.predict_batch(rows)

        items_out = [
            BatchPredictResultItem(
                index=p["index"],
                product_id=p["product_id"],
                location_id=p["location_id"],
                predicted_demand=p["predicted_demand"],
                confidence_score=p["confidence_score"],
                prediction_interval=PredictionInterval(**p["prediction_interval"]),
                model_used=p["model_used"],
                latency_ms=p["latency_ms"],
            )
            for p in predictions
        ]

        total_latency = round((time.perf_counter() - t0) * 1000, 2)
        data = BatchPredictData(
            total_items=len(items_out),
            predictions=items_out,
            model_used="XGBoost (batch-vectorized)",
            total_latency_ms=total_latency,
        )
        response = ApiResponse[BatchPredictData](
            success=True,
            message=f"Batch prediction completed for {len(items_out)} items.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())

    except Exception as exc:
        logger.exception("Batch prediction failed: %s", exc)
        return _error_response("Batch prediction failed.", [str(exc)], status_code=500)


# ---------------------------------------------------------------------------
# POST /forecast/{product_id}
# ---------------------------------------------------------------------------


@router.post(
    "/forecast/{product_id}",
    summary="N-day rolling product forecast",
    description=(
        "Generates a day-by-day demand forecast for a specific product at a "
        "given location for up to 365 days.\n\n"
        "Each day is predicted independently using the hybrid model with "
        "date-derived temporal features (month, quarter, day-of-year, "
        "month_sin, month_cos).  The response includes a trend indicator "
        "(INCREASING / DECREASING / STABLE) and a seasonality tag "
        "(HIGH / MEDIUM / NORMAL) for each day."
    ),
    tags=[_TAG],
    responses={
        200: {"description": "Forecast generated successfully."},
        422: {"description": "Validation error."},
        503: {"description": "Model not loaded."},
    },
)
async def generate_forecast(
    product_id: int = Path(..., description="Product SKU identifier.", ge=1),
    request: ForecastRequest = ...,
    svc: ForecastingService = Depends(get_forecast_service),
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    t0 = time.perf_counter()

    if not state.model_loaded:
        return _error_response(
            "Forecasting model is not loaded.",
            ["Model failed to load during startup."],
            status_code=503,
        )

    try:
        base_payload = request.model_dump()
        base_payload["product_id"] = product_id
        base_payload["location_id"] = request.location_id

        forecast_days = svc.generate_forecast(
            product_id=product_id,
            location_id=request.location_id,
            days=request.days,
            base_payload=base_payload,
        )

        forecast_items = [
            ForecastDayResult(
                date=d["date"],
                forecasted_demand=d["forecasted_demand"],
                confidence=d["confidence"],
                prediction_interval=PredictionInterval(**d["prediction_interval"]),
                trend=d["trend"],
                seasonality=d["seasonality"],
            )
            for d in forecast_days
        ]

        data = ForecastData(
            product_id=product_id,
            location_id=request.location_id,
            days_requested=request.days,
            days_returned=len(forecast_items),
            forecast=forecast_items,
        )
        response = ApiResponse[ForecastData](
            success=True,
            message=f"{len(forecast_items)}-day forecast generated for product {product_id}.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())

    except Exception as exc:
        logger.exception("Forecast generation failed for product %s: %s", product_id, exc)
        return _error_response("Forecast generation failed.", [str(exc)], status_code=500)


# ---------------------------------------------------------------------------
# POST /inventory/reorder
# ---------------------------------------------------------------------------


@router.post(
    "/inventory/reorder",
    summary="Reorder quantity recommendation",
    description=(
        "Computes the recommended replenishment order quantity for a single "
        "inventory position.\n\n"
        "If ``forecasted_demand`` is omitted in the request, the hybrid "
        "forecasting model is called automatically.  The response includes "
        "days until stockout, reorder urgency (CRITICAL / MODERATE / LOW), "
        "and model confidence."
    ),
    tags=[_TAG],
    responses={
        200: {"description": "Reorder recommendation generated."},
        422: {"description": "Validation error."},
        503: {"description": "Model not loaded."},
    },
)
async def reorder_recommendation(
    request: ReorderRequest,
    svc: ForecastingService = Depends(get_forecast_service),
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    t0 = time.perf_counter()

    if not state.model_loaded and request.forecasted_demand is None:
        return _error_response(
            "Forecasting model is not loaded and no forecasted_demand was provided.",
            ["Provide forecasted_demand or wait for the model to load."],
            status_code=503,
        )

    try:
        payload = request.model_dump()
        result = svc.reorder_recommendation(
            on_hand_qty=request.on_hand_qty,
            allocated_qty=request.allocated_qty,
            in_transit_qty=request.in_transit_qty,
            safety_stock_qty=request.safety_stock_qty,
            reorder_point_qty=request.reorder_point_qty,
            lead_time_days=request.lead_time_days,
            forecasted_demand=request.forecasted_demand,
            payload=payload,
        )

        data = ReorderData(
            product_id=request.product_id,
            location_id=request.location_id,
            recommended_reorder_qty=result["recommended_reorder_qty"],
            days_until_stockout=result["days_until_stockout"],
            reorder_urgency=result["reorder_urgency"],
            decision=result["decision"],
            forecasted_demand=result["forecasted_demand"],
            available_stock=result["available_stock"],
            projected_stock_after_lead_time=result["projected_stock_after_lead_time"],
            confidence=result["confidence"],
        )
        response = ApiResponse[ReorderData](
            success=True,
            message="Reorder recommendation generated successfully.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())

    except Exception as exc:
        logger.exception(
            "Reorder recommendation failed for product %s: %s", request.product_id, exc
        )
        return _error_response("Reorder recommendation failed.", [str(exc)], status_code=500)


# ---------------------------------------------------------------------------
# POST /inventory/risk
# ---------------------------------------------------------------------------


@router.post(
    "/inventory/risk",
    summary="Inventory risk assessment",
    description=(
        "Assesses inventory risk for a single product-location position and "
        "classifies it as LOW, MEDIUM, HIGH, or CRITICAL.\n\n"
        "Risk is computed from projected stock vs safety stock and reorder "
        "point thresholds, using the model's demand forecast when no "
        "``forecasted_demand`` is provided.  The response includes reason "
        "codes and a recommended action."
    ),
    tags=[_TAG],
    responses={
        200: {"description": "Risk assessment completed."},
        422: {"description": "Validation error."},
        503: {"description": "Model not loaded."},
    },
)
async def inventory_risk(
    request: RiskRequest,
    svc: ForecastingService = Depends(get_forecast_service),
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    t0 = time.perf_counter()

    if not state.model_loaded and request.forecasted_demand is None:
        return _error_response(
            "Forecasting model is not loaded and no forecasted_demand was provided.",
            ["Provide forecasted_demand or wait for the model to load."],
            status_code=503,
        )

    try:
        payload = request.model_dump()
        # Use current_stock as on_hand_qty for the model if on_hand_qty not given
        if payload.get("on_hand_qty") is None:
            payload["on_hand_qty"] = request.current_stock

        result = svc.risk_assessment(
            current_stock=request.current_stock,
            safety_stock_qty=request.safety_stock_qty,
            reorder_point_qty=request.reorder_point_qty,
            forecasted_demand=request.forecasted_demand,
            lead_time_days=request.lead_time_days,
            payload=payload,
        )

        data = RiskData(
            product_id=request.product_id,
            location_id=request.location_id,
            risk_level=result["risk_level"],
            risk_score=result["risk_score"],
            reason_codes=result["reason_codes"],
            recommended_action=result["recommended_action"],
            forecasted_demand=result["forecasted_demand"],
            current_stock=request.current_stock,
            projected_stock=result["projected_stock"],
            confidence=result["confidence"],
        )
        response = ApiResponse[RiskData](
            success=True,
            message=f"Risk assessment completed: {result['risk_level']}.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())

    except Exception as exc:
        logger.exception(
            "Risk assessment failed for product %s: %s", request.product_id, exc
        )
        return _error_response("Risk assessment failed.", [str(exc)], status_code=500)


# ---------------------------------------------------------------------------
# POST /simulate
# ---------------------------------------------------------------------------


@router.post(
    "/simulate",
    summary="What-if demand simulation",
    description=(
        "Performs a what-if scenario simulation by running the baseline "
        "prediction and then re-running it with the specified scenario "
        "overrides applied (promotion flag, price change, lead time change, "
        "safety stock adjustment, demand multiplier).\n\n"
        "Returns the original prediction, the simulated prediction, absolute "
        "and percentage deltas, an estimated revenue impact, and a plain-"
        "language recommendation."
    ),
    tags=[_TAG],
    responses={
        200: {"description": "Simulation completed."},
        422: {"description": "Validation error."},
        503: {"description": "Model not loaded."},
    },
)
async def simulate(
    request: SimulateRequest,
    svc: ForecastingService = Depends(get_forecast_service),
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    t0 = time.perf_counter()

    if not state.model_loaded:
        return _error_response(
            "Forecasting model is not loaded.",
            ["Model failed to load during startup."],
            status_code=503,
        )

    try:
        payload = request.model_dump()
        scenario = payload.pop("scenario", {})
        horizon = payload.pop("horizon_days", 14)

        result = svc.simulate(payload=payload, scenario=scenario, horizon=horizon)

        data = SimulateData(
            product_id=request.product_id,
            location_id=request.location_id,
            horizon_days=horizon,
            original=DemandPoint(
                predicted_demand=result["original"]["predicted_demand"],
                confidence=result["original"]["confidence"],
                prediction_interval=PredictionInterval(
                    **result["original"]["prediction_interval"]
                ),
            ),
            simulated=DemandPoint(
                predicted_demand=result["simulated"]["predicted_demand"],
                confidence=result["simulated"]["confidence"],
                applied_demand_multiplier=result["simulated"]["applied_demand_multiplier"],
            ),
            delta=DeltaInfo(**result["delta"]),
            business_impact=BusinessImpact(**result["business_impact"]),
            recommendation=result["recommendation"],
            scenario_applied=result["scenario_applied"],
        )
        response = ApiResponse[SimulateData](
            success=True,
            message="What-if simulation completed successfully.",
            data=data,
            metadata=_metadata(t0),
        )
        return JSONResponse(content=response.model_dump())

    except Exception as exc:
        logger.exception(
            "Simulation failed for product %s: %s", request.product_id, exc
        )
        return _error_response("Simulation failed.", [str(exc)], status_code=500)
