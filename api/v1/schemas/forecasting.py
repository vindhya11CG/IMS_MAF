"""Pydantic V2 request and response schemas for the demand-forecasting endpoints.

Every response is wrapped in the standard ``ApiResponse[T]`` envelope:

.. code-block:: json

    {
        "success": true,
        "message": "...",
        "data": { ... },
        "metadata": {
            "timestamp": "2026-07-11T17:00:00",
            "latency_ms": 42.3
        }
    }

Error responses use ``ErrorResponse``:

.. code-block:: json

    {
        "success": false,
        "message": "...",
        "errors": ["..."]
    }
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Generic envelope
# ---------------------------------------------------------------------------

DataT = TypeVar("DataT")


class ResponseMetadata(BaseModel):
    """Standard metadata block attached to every API response."""

    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of the response.")
    latency_ms: float = Field(..., description="End-to-end server latency in milliseconds.")


class ApiResponse(BaseModel, Generic[DataT]):
    """Standard success envelope returned by all forecasting endpoints."""

    success: bool = Field(True, description="Always ``true`` for a successful response.")
    message: str = Field(..., description="Human-readable status message.")
    data: DataT = Field(..., description="Response payload.")
    metadata: ResponseMetadata = Field(..., description="Response metadata.")


class ErrorResponse(BaseModel):
    """Standard error envelope returned on failures."""

    success: bool = Field(False, description="Always ``false`` for an error response.")
    message: str = Field(..., description="Human-readable error message.")
    errors: List[str] = Field(default_factory=list, description="List of error details.")


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class HealthData(BaseModel):
    """Payload returned by ``GET /health``."""

    api_status: str = Field(..., description="Current API status (e.g. 'healthy').")
    model_loaded: bool = Field(..., description="Whether the forecasting model is in memory.")
    model_loaded_at: Optional[str] = Field(
        None, description="ISO-8601 timestamp when the model was loaded."
    )
    version: str = Field(..., description="API version string.")
    uptime_seconds: float = Field(..., description="Seconds since the API process started.")


# ---------------------------------------------------------------------------
# /model/info
# ---------------------------------------------------------------------------


class ArtifactPaths(BaseModel):
    model: str
    metrics: str
    features: str


class TrainingDateRange(BaseModel):
    start: str
    end: str


class ModelInfoData(BaseModel):
    """Payload returned by ``GET /model/info``."""

    model_name: str
    algorithm: str
    training_date: str
    num_products: int
    num_locations: int
    num_categories: int
    dataset_size: int
    training_date_range: TrainingDateRange
    version: str
    artifact_paths: ArtifactPaths
    sarimax_weight: float
    xgboost_weight: float
    num_sarimax_models: int
    feature_count: int


# ---------------------------------------------------------------------------
# /model/metrics
# ---------------------------------------------------------------------------


class MetricsSection(BaseModel):
    """Metrics for a single train/val/test split."""

    accuracy_pct: Optional[float] = Field(None, description="Accuracy percentage.")
    mape_pct: Optional[float] = Field(None, description="Mean Absolute Percentage Error %.")
    mae_pct: Optional[float] = Field(None, description="Mean Absolute Error %.")
    rmse_pct: Optional[float] = Field(None, description="Root Mean Squared Error %.")
    r2_pct: Optional[float] = Field(None, description="R² score %.")


class ModelMetricsData(BaseModel):
    """Payload returned by ``GET /model/metrics``."""

    train_metrics: MetricsSection
    val_metrics: MetricsSection
    test_metrics: MetricsSection


# ---------------------------------------------------------------------------
# /features
# ---------------------------------------------------------------------------


class FeatureListData(BaseModel):
    """Payload returned by ``GET /features``."""

    feature_names: List[str]
    categorical_features: List[str]
    numerical_features: List[str]
    target_column: str
    feature_count: int


# ---------------------------------------------------------------------------
# /predict  (single)
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    """Request body for ``POST /predict``."""

    model_config = {"json_schema_extra": {"examples": [
        {
            "product_id": 1001,
            "location_id": 7,
            "on_hand_qty": 120,
            "allocated_qty": 20,
            "safety_stock_qty": 40,
            "reorder_point_qty": 60,
            "lead_time_days": 7,
            "avg_retail_price": 29.99,
            "category_id": 1,
            "velocity_class_id": 2,
            "horizon_days": 14,
        }
    ]}}

    product_id: int = Field(..., description="Product SKU identifier.", ge=1)
    location_id: int = Field(..., description="Location / warehouse identifier.", ge=1)
    on_hand_qty: int = Field(..., description="Current on-hand stock quantity.", ge=0)
    allocated_qty: int = Field(0, description="Quantity already allocated/reserved.", ge=0)
    safety_stock_qty: int = Field(..., description="Safety stock threshold.", ge=0)
    reorder_point_qty: int = Field(..., description="Reorder point threshold.", ge=0)
    lead_time_days: int = Field(7, description="Supplier lead time in days.", ge=0)
    is_promotional: bool = Field(False, description="Whether a promotional period is active.")
    annual_units_max: int = Field(0, description="Annual throughput cap for velocity scoring.", ge=0)
    avg_retail_price: float = Field(0.0, description="Average retail price per unit.", ge=0.0)
    holding_cost_per_unit_day: float = Field(0.0, description="Holding cost per unit per day.", ge=0.0)
    handling_cost_per_unit: float = Field(0.0, description="Handling cost per unit.", ge=0.0)
    order_fulfillment_rate: float = Field(0.0, description="Historical order fulfillment rate (0–1).", ge=0.0, le=1.0)
    total_orders_last_month: int = Field(0, description="Total orders placed last month.", ge=0)
    turnover_ratio: float = Field(0.0, description="Inventory turnover ratio.", ge=0.0)
    demand_std_dev: float = Field(0.0, description="Historical demand standard deviation.", ge=0.0)
    season_multiplier: float = Field(1.0, description="Seasonal demand multiplier.", ge=0.0)
    category_id: int = Field(0, description="Product category identifier.", ge=0)
    velocity_class_id: int = Field(0, description="Velocity class identifier.", ge=0)
    horizon_days: int = Field(14, description="Forecast horizon in days.", ge=1, le=365)
    # Phase 6: Weather & Festival fields
    weather_demand_multiplier: Optional[float] = Field(1.0, description="Weather-based demand multiplier.", ge=0.0)
    weather_severity_index: Optional[float] = Field(0.0, description="Weather severity index (0.0 to 1.0).", ge=0.0, le=1.0)
    is_festival_day: Optional[bool] = Field(False, description="Whether today is a festival day.")
    festival_proximity_score: Optional[float] = Field(0.0, description="Proximity score to the nearest festival (0.0 to 1.0).", ge=0.0, le=1.0)
    is_shopping_season: Optional[bool] = Field(False, description="Whether an active shopping season is underway.")
    supply_disruption_risk: Optional[float] = Field(0.0, description="Supply disruption risk score (0.0 to 1.0).", ge=0.0, le=1.0)
    climate_anomaly_score: Optional[float] = Field(0.0, description="Climate anomaly score (0.0 to 1.0).", ge=0.0, le=1.0)
    regional_demand_index: Optional[float] = Field(1.0, description="Regional demand index multiplier.", ge=0.0)


class PredictionInterval(BaseModel):
    lower: float
    upper: float


class PredictData(BaseModel):
    """Payload returned by ``POST /predict``."""

    product_id: int
    location_id: int
    predicted_demand: float
    confidence_score: float
    prediction_interval: PredictionInterval
    model_used: str
    horizon_days: int
    latency_ms: float


# ---------------------------------------------------------------------------
# /predict/batch
# ---------------------------------------------------------------------------


class BatchPredictItem(BaseModel):
    """Single item in a batch prediction request."""

    product_id: int = Field(..., ge=1)
    location_id: int = Field(..., ge=1)
    on_hand_qty: int = Field(..., ge=0)
    allocated_qty: int = Field(0, ge=0)
    safety_stock_qty: int = Field(..., ge=0)
    reorder_point_qty: int = Field(..., ge=0)
    lead_time_days: int = Field(7, ge=0)
    is_promotional: bool = Field(False)
    annual_units_max: int = Field(0, ge=0)
    avg_retail_price: float = Field(0.0, ge=0.0)
    holding_cost_per_unit_day: float = Field(0.0, ge=0.0)
    handling_cost_per_unit: float = Field(0.0, ge=0.0)
    order_fulfillment_rate: float = Field(0.0, ge=0.0, le=1.0)
    total_orders_last_month: int = Field(0, ge=0)
    turnover_ratio: float = Field(0.0, ge=0.0)
    demand_std_dev: float = Field(0.0, ge=0.0)
    season_multiplier: float = Field(1.0, ge=0.0)
    category_id: int = Field(0, ge=0)
    velocity_class_id: int = Field(0, ge=0)
    # Phase 6: Weather & Festival fields
    weather_demand_multiplier: Optional[float] = Field(1.0, ge=0.0)
    weather_severity_index: Optional[float] = Field(0.0, ge=0.0, le=1.0)
    is_festival_day: Optional[bool] = Field(False)
    festival_proximity_score: Optional[float] = Field(0.0, ge=0.0, le=1.0)
    is_shopping_season: Optional[bool] = Field(False)
    supply_disruption_risk: Optional[float] = Field(0.0, ge=0.0, le=1.0)
    climate_anomaly_score: Optional[float] = Field(0.0, ge=0.0, le=1.0)
    regional_demand_index: Optional[float] = Field(1.0, ge=0.0)


class BatchPredictRequest(BaseModel):
    """Request body for ``POST /predict/batch``."""

    model_config = {"json_schema_extra": {"examples": [
        {
            "items": [
                {
                    "product_id": 1001,
                    "location_id": 7,
                    "on_hand_qty": 120,
                    "allocated_qty": 20,
                    "safety_stock_qty": 40,
                    "reorder_point_qty": 60,
                },
                {
                    "product_id": 1002,
                    "location_id": 3,
                    "on_hand_qty": 80,
                    "allocated_qty": 0,
                    "safety_stock_qty": 20,
                    "reorder_point_qty": 35,
                },
            ]
        }
    ]}}

    items: List[BatchPredictItem] = Field(
        ..., description="List of inventory items to predict demand for.", min_length=1
    )

    @field_validator("items")
    @classmethod
    def max_batch_size(cls, v: List[BatchPredictItem]) -> List[BatchPredictItem]:
        if len(v) > 5_000:
            raise ValueError("Batch size cannot exceed 5,000 items per request.")
        return v


class BatchPredictResultItem(BaseModel):
    index: int
    product_id: Optional[int]
    location_id: Optional[int]
    predicted_demand: float
    confidence_score: float
    prediction_interval: PredictionInterval
    model_used: str
    latency_ms: float


class BatchPredictData(BaseModel):
    """Payload returned by ``POST /predict/batch``."""

    total_items: int
    predictions: List[BatchPredictResultItem]
    model_used: str
    total_latency_ms: float


# ---------------------------------------------------------------------------
# /forecast/{product_id}
# ---------------------------------------------------------------------------


class ForecastRequest(BaseModel):
    """Request body for ``POST /forecast/{product_id}``."""

    model_config = {"json_schema_extra": {"examples": [
        {
            "days": 30,
            "location_id": 7,
            "on_hand_qty": 120,
            "allocated_qty": 20,
            "safety_stock_qty": 40,
            "reorder_point_qty": 60,
        }
    ]}}

    days: int = Field(..., description="Number of forecast days to generate.", ge=1, le=365)
    location_id: int = Field(..., description="Location identifier.", ge=1)
    on_hand_qty: int = Field(0, ge=0)
    allocated_qty: int = Field(0, ge=0)
    safety_stock_qty: int = Field(0, ge=0)
    reorder_point_qty: int = Field(0, ge=0)
    lead_time_days: int = Field(7, ge=0)
    avg_retail_price: float = Field(0.0, ge=0.0)
    category_id: int = Field(0, ge=0)
    velocity_class_id: int = Field(0, ge=0)
    season_multiplier: float = Field(1.0, ge=0.0)
    is_promotional: bool = Field(False)
    annual_units_max: int = Field(0, ge=0)
    holding_cost_per_unit_day: float = Field(0.0, ge=0.0)
    handling_cost_per_unit: float = Field(0.0, ge=0.0)
    order_fulfillment_rate: float = Field(0.0, ge=0.0, le=1.0)
    total_orders_last_month: int = Field(0, ge=0)
    turnover_ratio: float = Field(0.0, ge=0.0)
    demand_std_dev: float = Field(0.0, ge=0.0)


class ForecastDayResult(BaseModel):
    date: str
    forecasted_demand: float
    confidence: float
    prediction_interval: PredictionInterval
    trend: str = Field(..., description="INCREASING | DECREASING | STABLE")
    seasonality: str = Field(..., description="HIGH | MEDIUM | NORMAL")


class ForecastData(BaseModel):
    """Payload returned by ``POST /forecast/{product_id}``."""

    product_id: int
    location_id: int
    days_requested: int
    days_returned: int
    forecast: List[ForecastDayResult]


# ---------------------------------------------------------------------------
# /inventory/reorder
# ---------------------------------------------------------------------------


class ReorderRequest(BaseModel):
    """Request body for ``POST /inventory/reorder``."""

    model_config = {"json_schema_extra": {"examples": [
        {
            "product_id": 1001,
            "location_id": 7,
            "on_hand_qty": 50,
            "allocated_qty": 10,
            "in_transit_qty": 5,
            "safety_stock_qty": 40,
            "reorder_point_qty": 60,
            "lead_time_days": 7,
        }
    ]}}

    product_id: int = Field(..., ge=1)
    location_id: int = Field(..., ge=1)
    on_hand_qty: int = Field(..., ge=0)
    allocated_qty: int = Field(0, ge=0)
    in_transit_qty: int = Field(0, ge=0)
    safety_stock_qty: int = Field(..., ge=0)
    reorder_point_qty: int = Field(..., ge=0)
    lead_time_days: int = Field(14, ge=0)
    forecasted_demand: Optional[float] = Field(
        None,
        description="Pre-computed demand forecast. If omitted the model will estimate it.",
    )
    # Optional extra features for the model when forecasted_demand is None
    avg_retail_price: float = Field(0.0, ge=0.0)
    category_id: int = Field(0, ge=0)
    velocity_class_id: int = Field(0, ge=0)
    season_multiplier: float = Field(1.0, ge=0.0)
    annual_units_max: int = Field(0, ge=0)
    is_promotional: bool = Field(False)
    holding_cost_per_unit_day: float = Field(0.0, ge=0.0)
    handling_cost_per_unit: float = Field(0.0, ge=0.0)
    order_fulfillment_rate: float = Field(0.0, ge=0.0, le=1.0)
    total_orders_last_month: int = Field(0, ge=0)
    turnover_ratio: float = Field(0.0, ge=0.0)
    demand_std_dev: float = Field(0.0, ge=0.0)


class ReorderData(BaseModel):
    """Payload returned by ``POST /inventory/reorder``."""

    product_id: int
    location_id: int
    recommended_reorder_qty: float
    days_until_stockout: int
    reorder_urgency: str = Field(..., description="CRITICAL | MODERATE | LOW")
    decision: str
    forecasted_demand: float
    available_stock: int
    projected_stock_after_lead_time: float
    confidence: float


# ---------------------------------------------------------------------------
# /inventory/risk
# ---------------------------------------------------------------------------


class RiskRequest(BaseModel):
    """Request body for ``POST /inventory/risk``."""

    model_config = {"json_schema_extra": {"examples": [
        {
            "product_id": 1001,
            "location_id": 7,
            "current_stock": 35,
            "safety_stock_qty": 40,
            "reorder_point_qty": 60,
            "lead_time_days": 7,
        }
    ]}}

    product_id: int = Field(..., ge=1)
    location_id: int = Field(..., ge=1)
    current_stock: int = Field(..., ge=0)
    safety_stock_qty: int = Field(..., ge=0)
    reorder_point_qty: int = Field(..., ge=0)
    lead_time_days: int = Field(14, ge=0)
    forecasted_demand: Optional[float] = Field(
        None,
        description="Pre-computed demand forecast. If omitted the model will estimate it.",
    )
    avg_retail_price: float = Field(0.0, ge=0.0)
    category_id: int = Field(0, ge=0)
    velocity_class_id: int = Field(0, ge=0)
    season_multiplier: float = Field(1.0, ge=0.0)
    annual_units_max: int = Field(0, ge=0)
    is_promotional: bool = Field(False)
    allocated_qty: int = Field(0, ge=0)
    on_hand_qty: Optional[int] = Field(None, ge=0)
    holding_cost_per_unit_day: float = Field(0.0, ge=0.0)
    handling_cost_per_unit: float = Field(0.0, ge=0.0)
    order_fulfillment_rate: float = Field(0.0, ge=0.0, le=1.0)
    total_orders_last_month: int = Field(0, ge=0)
    turnover_ratio: float = Field(0.0, ge=0.0)
    demand_std_dev: float = Field(0.0, ge=0.0)


class RiskData(BaseModel):
    """Payload returned by ``POST /inventory/risk``."""

    product_id: int
    location_id: int
    risk_level: str = Field(..., description="LOW | MEDIUM | HIGH | CRITICAL")
    risk_score: float = Field(..., ge=0.0, le=100.0)
    reason_codes: List[str]
    recommended_action: str
    forecasted_demand: float
    current_stock: int
    projected_stock: float
    confidence: float


# ---------------------------------------------------------------------------
# /simulate
# ---------------------------------------------------------------------------


class ScenarioParams(BaseModel):
    """What-if scenario parameters for ``POST /simulate``."""

    demand_multiplier: float = Field(
        1.0,
        description="Multiply the forecasted demand by this factor (e.g. 1.3 = +30 %).",
        ge=0.0,
    )
    is_promotional: Optional[bool] = Field(
        None, description="Override the promotional flag for the scenario."
    )
    lead_time_days: Optional[int] = Field(
        None, description="Override the lead time in days.", ge=0
    )
    price_change_pct: Optional[float] = Field(
        None,
        description="Percentage change to apply to avg_retail_price (e.g. -10 = −10 %).",
    )
    safety_stock_change: Optional[int] = Field(
        None,
        description="Absolute unit change to apply to safety_stock_qty (e.g. 50 = +50 units).",
    )


class SimulateRequest(BaseModel):
    """Request body for ``POST /simulate``."""

    model_config = {"json_schema_extra": {"examples": [
        {
            "product_id": 1001,
            "location_id": 7,
            "on_hand_qty": 120,
            "allocated_qty": 20,
            "safety_stock_qty": 40,
            "reorder_point_qty": 60,
            "avg_retail_price": 29.99,
            "category_id": 1,
            "velocity_class_id": 2,
            "horizon_days": 14,
            "scenario": {
                "demand_multiplier": 1.3,
                "is_promotional": True,
                "price_change_pct": -5.0,
            },
        }
    ]}}

    product_id: int = Field(..., ge=1)
    location_id: int = Field(..., ge=1)
    on_hand_qty: int = Field(..., ge=0)
    allocated_qty: int = Field(0, ge=0)
    safety_stock_qty: int = Field(..., ge=0)
    reorder_point_qty: int = Field(..., ge=0)
    lead_time_days: int = Field(7, ge=0)
    is_promotional: bool = Field(False)
    annual_units_max: int = Field(0, ge=0)
    avg_retail_price: float = Field(0.0, ge=0.0)
    holding_cost_per_unit_day: float = Field(0.0, ge=0.0)
    handling_cost_per_unit: float = Field(0.0, ge=0.0)
    order_fulfillment_rate: float = Field(0.0, ge=0.0, le=1.0)
    total_orders_last_month: int = Field(0, ge=0)
    turnover_ratio: float = Field(0.0, ge=0.0)
    demand_std_dev: float = Field(0.0, ge=0.0)
    season_multiplier: float = Field(1.0, ge=0.0)
    category_id: int = Field(0, ge=0)
    velocity_class_id: int = Field(0, ge=0)
    horizon_days: int = Field(14, ge=1, le=365)
    scenario: ScenarioParams = Field(..., description="Scenario overrides to apply.")


class DemandPoint(BaseModel):
    predicted_demand: float
    confidence: float
    prediction_interval: Optional[PredictionInterval] = None
    applied_demand_multiplier: Optional[float] = None


class DeltaInfo(BaseModel):
    absolute: float
    percentage: float


class BusinessImpact(BaseModel):
    revenue_impact_estimate: float
    currency: str


class SimulateData(BaseModel):
    """Payload returned by ``POST /simulate``."""

    product_id: int
    location_id: int
    horizon_days: int
    original: DemandPoint
    simulated: DemandPoint
    delta: DeltaInfo
    business_impact: BusinessImpact
    recommendation: str
    scenario_applied: Dict[str, Any]
