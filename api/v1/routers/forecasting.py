"""Demand Forecasting API router.

All 10 endpoints are implemented here as thin controllers.
Business logic lives entirely in :class:`ForecastingService`.

Mount prefix: ``/api/v1/forecasting``
Tag group:    ``Demand Forecasting``
"""
from __future__ import annotations

import logging
import time
from calendar import monthrange
from datetime import date, datetime, timezone, timedelta
from pathlib import Path as PathlibPath
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import FileResponse, JSONResponse

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
from utils.csv_loader import CsvInventoryDataLoader

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


def _get_country_code_from_state_code(state_code: str | None) -> str:
    if not state_code:
        return "US"
    if "-" in state_code:
        return state_code.split("-")[0].upper()
    return state_code.upper()


def _parse_optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        try:
            return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None


def _same_annual_day(start_date: date | None, end_date: date | None, target_date: date) -> bool:
    if start_date is None:
        return False
    if end_date is None:
        end_date = start_date
    if start_date.month != target_date.month or end_date.month != target_date.month:
        return False
    return start_date.day <= target_date.day <= end_date.day


def _find_festival_calendar_context(
    festivals: List[Dict[str, Any]],
    location_id: int,
    target_date: date,
) -> Dict[str, Any]:
    if not festivals:
        return {}

    # Match location-specific festivals or national festivals
    relevant_festivals = [
        row
        for row in festivals
        if int(str(row.get("location_id") or 0)) == location_id
        or str(row.get("festival_type", "")).upper() == "NATIONAL"
    ]
    if not relevant_festivals:
        relevant_festivals = festivals

    nearest_festival = None
    nearest_distance = None

    for festival in relevant_festivals:
        raw_start = _parse_optional_date(festival.get("start_date"))
        raw_end = _parse_optional_date(festival.get("end_date")) or raw_start
        if raw_start is None:
            continue
        if raw_end is None:
            raw_end = raw_start

        # Map start_date and end_date to target_date's year
        try:
            start_date = date(target_date.year, raw_start.month, raw_start.day)
        except ValueError:
            start_date = date(target_date.year, raw_start.month, 28)

        try:
            end_date = date(target_date.year, raw_end.month, raw_end.day)
        except ValueError:
            end_date = date(target_date.year, raw_end.month, 28)

        if end_date < start_date:
            end_date = date(target_date.year + 1, raw_end.month, raw_end.day)

        if start_date <= target_date <= end_date:
            return {
                "festival_calendar_name": festival.get("festival_name"),
                "festival_calendar_type": festival.get("festival_type"),
                "festival_calendar_demand_lift_pct": float(
                    str(festival.get("demand_lift_pct", 0.0)) or 0.0
                ),
                "festival_calendar_supply_risk_score": float(
                    str(festival.get("supply_risk_score", 0.0)) or 0.0
                ),
                "festival_calendar_start_date": start_date.isoformat(),
                "festival_calendar_end_date": end_date.isoformat(),
                "festival_calendar_status": "active",
                "festival_calendar_proximity_score": 1.0,
            }

        if target_date < start_date:
            distance = (start_date - target_date).days
        else:
            distance = (target_date - end_date).days

        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_festival = (festival, start_date, end_date)

    if nearest_festival is not None and nearest_distance is not None and nearest_distance <= 7:
        festival, start_date, end_date = nearest_festival
        proximity_score = round(max(0.0, min(1.0, 1.0 - nearest_distance / 7.0)), 2)
        return {
            "festival_calendar_name": festival.get("festival_name"),
            "festival_calendar_type": festival.get("festival_type"),
            "festival_calendar_demand_lift_pct": float(
                str(festival.get("demand_lift_pct", 0.0)) or 0.0
            ),
            "festival_calendar_supply_risk_score": float(
                str(festival.get("supply_risk_score", 0.0)) or 0.0
            ),
            "festival_calendar_start_date": start_date.isoformat(),
            "festival_calendar_end_date": end_date.isoformat(),
            "festival_calendar_status": "proximity",
            "festival_calendar_proximity_score": proximity_score,
        }

    return {}


def _find_location_climate_profile(
    profiles: List[Dict[str, Any]],
    location_id: int,
) -> Dict[str, Any]:
    if not profiles:
        return {}
    return next(
        (
            profile
            for profile in profiles
            if int(str(profile.get("location_id") or 0)) == location_id
        ),
        {},
    )


def _resolve_timeline_events(
    ctx: Dict[str, Any],
    festival_ctx: Dict[str, Any],
    climate_profile: Dict[str, Any],
    current_date: date,
) -> List[Dict[str, str]]:
    festival_score = float(str(ctx.get("festival_proximity_score", 0.0)) or 0.0)
    weather_severity = float(str(ctx.get("weather_severity_index", 0.0)) or 0.0)
    events: List[Dict[str, str]] = []

    if festival_ctx.get("festival_calendar_status") == "active":
        festival_name = festival_ctx.get("festival_calendar_name") or "Festival"
        festival_type = festival_ctx.get("festival_calendar_type") or "Festival"
        events.append(
            {
                "event_type": "festival",
                "event_detail": f"{festival_name} ({festival_type})",
            }
        )
    elif festival_ctx.get("festival_calendar_status") == "proximity":
        proximity_score = float(
            str(festival_ctx.get("festival_calendar_proximity_score", 0.0)) or 0.0
        )
        if proximity_score >= 0.5:
            festival_name = festival_ctx.get("festival_calendar_name") or "Festival"
            events.append(
                {
                    "event_type": "festival",
                    "event_detail": f"{festival_name} proximity {proximity_score:.2f}",
                }
            )

    weather_flags = any(
        str(ctx.get(k, 0)) in ("1", "True", "true")
        for k in [
            "heatwave_flag",
            "coldwave_flag",
            "monsoon_flag",
            "heavy_rain_flag",
            "extreme_weather_flag",
        ]
    )
    if weather_flags or weather_severity >= 0.75:
        events.append(
            {
                "event_type": "weather",
                "event_detail": f"Weather Extreme (severity={weather_severity:.2f})",
            }
        )

    # Treat Friday, Saturday, Sunday as weekend-style demand (Friday included)
    if current_date.weekday() >= 4:
        events.append({"event_type": "weekend", "event_detail": "Weekend"})

    return events


def _advance_timeline_date(current_date: date, horizon: str) -> date:
    if horizon == "monthly":
        next_month = current_date.month + 1
        next_year = current_date.year + (next_month - 1) // 12
        next_month = (next_month - 1) % 12 + 1
        next_day = min(current_date.day, monthrange(next_year, next_month)[1])
        return current_date.replace(year=next_year, month=next_month, day=next_day)
    if horizon == "3-months":
        new_month = current_date.month + 3
        new_year = current_date.year + (new_month - 1) // 12
        new_month = (new_month - 1) % 12 + 1
        new_day = min(current_date.day, monthrange(new_year, new_month)[1])
        return current_date.replace(year=new_year, month=new_month, day=new_day)
    if horizon == "6-months":
        new_month = current_date.month + 6
        new_year = current_date.year + (new_month - 1) // 12
        new_month = (new_month - 1) % 12 + 1
        new_day = min(current_date.day, monthrange(new_year, new_month)[1])
        return current_date.replace(year=new_year, month=new_month, day=new_day)
    if horizon == "yearly":
        try:
            return current_date.replace(year=current_date.year + 1)
        except ValueError:
            return current_date.replace(year=current_date.year + 1, day=28)
    return current_date + timedelta(days={"1-day": 1, "7-day": 7, "14-day": 14, "30-day": 30}.get(horizon, 1))


def _build_timeline_dates(start_date: date, horizon: str) -> List[date]:
    """Return a list of dates to render for the given horizon.

    Rules:
    - '1-day'  : today and tomorrow (2 points)
    - '7-day'  : today through next Thursday (8 points)
    - '14-day' : today through day 14 inclusive (15 points)
    - '30-day' : today through day 30 inclusive (31 points)
    - 'monthly','3-months','6-months','yearly': sequence of 8 anchors spaced by horizon increments
    """
    if horizon == "1-day":
        return [start_date + timedelta(days=i) for i in range(2)]
    if horizon == "7-day":
        return [start_date + timedelta(days=i) for i in range(8)]
    if horizon == "14-day":
        return [start_date + timedelta(days=i) for i in range(15)]
    if horizon == "30-day":
        return [start_date + timedelta(days=i) for i in range(31)]

    anchors = []
    cur = start_date
    for _ in range(8):
        anchors.append(cur)
        cur = _advance_timeline_date(cur, horizon)
    return anchors


def _build_timeline_dates_with_festivals(
    start_date: date,
    horizon: str,
    festivals: List[Dict[str, Any]],
    location_id: int,
) -> List[date]:
    base_dates = _build_timeline_dates(start_date, horizon)
    if not festivals or horizon in ("1-day", "7-day", "14-day", "30-day"):
        return base_dates

    max_date = base_dates[-1]
    years_to_check = set(range(start_date.year, max_date.year + 1))

    festival_dates = set()
    relevant_festivals = [
        row for row in festivals
        if int(str(row.get("location_id") or 0)) == location_id
        or str(row.get("festival_type", "")).upper() == "NATIONAL"
    ]
    if not relevant_festivals:
        relevant_festivals = festivals

    for fest in relevant_festivals:
        raw_start = _parse_optional_date(fest.get("start_date"))
        raw_end = _parse_optional_date(fest.get("end_date")) or raw_start
        if raw_start is None:
            continue
        if raw_end is None:
            raw_end = raw_start

        for y in years_to_check:
            try:
                f_start = date(y, raw_start.month, raw_start.day)
            except ValueError:
                f_start = date(y, raw_start.month, 28)

            try:
                f_end = date(y, raw_end.month, raw_end.day)
            except ValueError:
                f_end = date(y, raw_end.month, 28)

            if start_date <= f_start <= max_date:
                festival_dates.add(f_start)
            if start_date <= f_end <= max_date:
                festival_dates.add(f_end)

    return sorted(list(set(base_dates).union(festival_dates)))


@router.get(
    "/frontend/options",
    summary="Frontend demo options",
    description="Returns products, locations, and warehouses for the demand graph demo UI.",
    tags=[_TAG],
)
async def get_frontend_options() -> JSONResponse:
    loader = CsvInventoryDataLoader()
    products = loader.load_products()
    locations = loader.load_locations()
    warehouses = loader.load_distribution_centers()

    payload = {
        "products": [
            {
                "id": item.get("sku_id"),
                "name": item.get("product_name") or item.get("product_code") or f"Product {item.get('sku_id')}",
                "code": item.get("product_code"),
            }
            for item in products
            if item.get("sku_id") is not None
        ],
        "locations": [
            {
                "id": item.get("location_id"),
                "name": item.get("location_name") or item.get("city") or f"Location {item.get('location_id')}",
                "city": item.get("city"),
            }
            for item in locations
        ],
        "warehouses": [
            {
                "id": item.get("dc_id"),
                "name": item.get("dc_name") or f"Warehouse {item.get('dc_id')}",
                "city": item.get("city"),
            }
            for item in warehouses
        ],
        # mapping of location_id -> list of warehouse ids that serve that location
    }

    # build a mapping of location_id -> list of warehouse ids by location country fallback
    try:
        states = loader.load_states()
        state_country = {
            s.get("state_id"): _get_country_code_from_state_code(s.get("state_abbrev") or s.get("state_code"))
            for s in states
        }
        loc_map = {}
        for loc in locations:
            lid = loc.get("location_id")
            state = loc.get("state_id")
            if lid is None:
                continue
            location_country = state_country.get(state)
            loc_map[str(lid)] = [
                w.get("dc_id")
                for w in warehouses
                if w.get("state_id") == state
                or (location_country is not None and state_country.get(w.get("state_id")) == location_country)
            ]
        payload["location_warehouses"] = loc_map
    except Exception:
        payload["location_warehouses"] = {}
    return JSONResponse(content=payload)


def _find_weather_festival_context(
    loader: CsvInventoryDataLoader,
    product_id: int,
    location_id: int,
    target_date: datetime.date,
) -> Dict[str, Any]:
    try:
        rows = loader.load_demand_context_fact()
        candidates = [
            row
            for row in rows
            if row.get("product_id") == product_id and row.get("location_id") == location_id
        ]
        if not candidates:
            return {}

        def _event_strength(row: Dict[str, Any]) -> float:
            festival_score = float(str(row.get("festival_proximity_score", 0.0)) or 0.0)
            weather_severity = float(str(row.get("weather_severity_index", 0.0)) or 0.0)
            flags = any(
                str(row.get(key, 0)) in ("1", "True", "true")
                for key in [
                    "heatwave_flag",
                    "coldwave_flag",
                    "monsoon_flag",
                    "heavy_rain_flag",
                    "extreme_weather_flag",
                ]
            )
            festival_flag = str(row.get("is_festival_day", 0)) in ("1", "True", "true")
            return (1.0 if festival_flag else 0.0) + (1.0 if flags else 0.0) + festival_score + weather_severity

        exact = [
            row
            for row in candidates
            if _parse_optional_date(row.get("date")) == target_date
        ]
        context_row = exact[0] if exact else None

        if not context_row:
            same_month_day_rows = [
                row
                for row in candidates
                if _parse_optional_date(row.get("date")) is not None
                and _parse_optional_date(row.get("date")).month == target_date.month
                and _parse_optional_date(row.get("date")).day == target_date.day
            ]
            if same_month_day_rows:
                context_row = max(same_month_day_rows, key=_event_strength)

        if not context_row:
            dated_rows = [
                row
                for row in candidates
                if _parse_optional_date(row.get("date")) is not None
            ]
            nearest_row = min(
                dated_rows,
                key=lambda r: abs((_parse_optional_date(r.get("date")) - target_date).days),
            ) if dated_rows else None
            if nearest_row is not None:
                nearest_date = _parse_optional_date(nearest_row.get("date"))
                if abs((nearest_date - target_date).days) <= 7:
                    context_row = nearest_row

        if not context_row:
            return {}

        if _event_strength(context_row) <= 0.0:
            return {}

        return {
            "weather_demand_multiplier": context_row.get("weather_demand_multiplier"),
            "weather_severity_index": context_row.get("weather_severity_index"),
            "is_festival_day": context_row.get("is_festival_day"),
            "festival_proximity_score": context_row.get("festival_proximity_score"),
            "is_shopping_season": context_row.get("is_shopping_season"),
            "supply_disruption_risk": context_row.get("supply_disruption_risk"),
            "climate_anomaly_score": context_row.get("climate_anomaly_score"),
            "regional_demand_index": context_row.get("regional_demand_index"),
        }
    except Exception:
        return {}


@router.get(
    "/frontend/demo",
    summary="Frontend demo page",
    description="Serves the HTML demo page for exploring demand horizons in a browser.",
    tags=[_TAG],
)
async def get_frontend_demo_page() -> FileResponse:
    html_path = PathlibPath(__file__).resolve().parents[3] / "frontend" / "demand_graph_demo.html"
    return FileResponse(html_path, media_type="text/html")


@router.get(
    "/frontend/horizon-graph",
    summary="Demand graph data for the frontend demo",
    description="Generates 7-day, 14-day, 30-day, 90-day, and 365-day demand points using the forecasting model.",
    tags=[_TAG],
)
async def get_frontend_horizon_graph(
    product_id: int,
    location_id: int,
    warehouse_id: int | None = None,
    svc: ForecastingService = Depends(get_forecast_service),
) -> JSONResponse:
    loader = CsvInventoryDataLoader()
    products = {item.get("sku_id"): item for item in loader.load_products()}
    locations = {item.get("location_id"): item for item in loader.load_locations()}
    warehouses = {item.get("dc_id"): item for item in loader.load_distribution_centers()}
    positions = list(loader.load_inventory_positions())

    product = products.get(product_id, {})
    location = locations.get(location_id, {})
    warehouse = warehouses.get(warehouse_id) if warehouse_id is not None else None

    matching_position = next(
        (
            pos
            for pos in positions
            if getattr(pos, "sku_id", None) == product_id and getattr(pos, "location_id", None) == location_id
        ),
        None,
    )

    payload = {
        "product_id": product_id,
        "location_id": location_id,
        "on_hand_qty": getattr(matching_position, "on_hand_qty", 0) if matching_position else 0,
        "allocated_qty": getattr(matching_position, "allocated_qty", 0) if matching_position else 0,
        "safety_stock_qty": getattr(matching_position, "safety_stock_qty", 0) if matching_position else 0,
        "reorder_point_qty": getattr(matching_position, "reorder_point_qty", 0) if matching_position else 0,
        "avg_retail_price": float(product.get("avg_retail_price", 0) or 0),
        "annual_units_max": int(product.get("annual_units_max", 10000) or 10000),
        "category_id": int(product.get("category_id", 0) or 0),
        "velocity_class_id": int(product.get("velocity_class_id", 0) or 0),
        "is_promotional": False,
    }

    base_date = datetime.now().date()
    horizons = [
        ("7-day", 7),
        ("14-day", 14),
        ("30-day", 30),
        ("90-day", 90),
        ("365-day", 365),
    ]
    series = []
    for label, horizon in horizons:
        target_date = base_date + timedelta(days=horizon)
        horizon_payload = {
            **payload,
            "date": target_date.isoformat(),
            **_find_weather_festival_context(loader, product_id, location_id, target_date),
        }
        result = svc.predict_single(horizon_payload, horizon=horizon)
        series.append(
            {
                "label": label,
                "days": horizon,
                "forecast": round(result.get("predicted_demand", 0), 2),
                "confidence": round(result.get("confidence_score", 90.0), 2),
            }
        )

    return JSONResponse(
        content={
            "product": {"id": product_id, "name": product.get("product_name") or product.get("product_code")},
            "location": {"id": location_id, "name": location.get("location_name") or location.get("city")},
            "warehouse": {"id": warehouse_id, "name": warehouse.get("dc_name") if warehouse else None},
            "series": series,
        }
    )


@router.get(
    "/frontend/timeline-graph",
    summary="Demand timeline data for the frontend demo",
    description=(
        "Generates a demand forecast timeline from today onward using the selected forecast horizon."
    ),
    tags=[_TAG],
)
async def get_frontend_timeline_graph(
    product_id: int,
    location_id: int,
    warehouse_id: int | None = None,
    horizon: str = "1-day",
    svc: ForecastingService = Depends(get_forecast_service),
) -> JSONResponse:
    valid_horizons = {
        "1-day": 1,
        "7-day": 7,
        "14-day": 14,
        "30-day": 30,
        "monthly": 30,
        "3-months": 90,
        "6-months": 180,
        "yearly": 365,
    }
    if horizon not in valid_horizons:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported horizon '{horizon}'. Valid options are: {', '.join(valid_horizons)}.",
        )

    loader = CsvInventoryDataLoader()
    products = {item.get("sku_id"): item for item in loader.load_products()}
    locations = {item.get("location_id"): item for item in loader.load_locations()}
    warehouses = {item.get("dc_id"): item for item in loader.load_distribution_centers()}
    positions = list(loader.load_inventory_positions())
    in_transit_inventory = loader.load_in_transit_inventory()

    product = products.get(product_id, {})
    location = locations.get(location_id, {})
    warehouse = warehouses.get(warehouse_id) if warehouse_id is not None else None

    matching_position = next(
        (
            pos
            for pos in positions
            if getattr(pos, "sku_id", None) == product_id and getattr(pos, "location_id", None) == location_id
        ),
        None,
    )

    in_transit_qty = sum(
        item.get("quantity_in_transit", 0)
        for item in in_transit_inventory
        if int(item.get("sku_id", 0)) == product_id and int(item.get("location_id", 0)) == location_id
    )

    payload = {
        "product_id": product_id,
        "location_id": location_id,
        "on_hand_qty": getattr(matching_position, "on_hand_qty", 0) if matching_position else 0,
        "allocated_qty": getattr(matching_position, "allocated_qty", 0) if matching_position else 0,
        "safety_stock_qty": getattr(matching_position, "safety_stock_qty", 0) if matching_position else 0,
        "reorder_point_qty": getattr(matching_position, "reorder_point_qty", 0) if matching_position else 0,
        "avg_retail_price": float(product.get("avg_retail_price", 0) or 0),
        "annual_units_max": int(product.get("annual_units_max", 10000) or 10000),
        "category_id": int(product.get("category_id", 0) or 0),
        "velocity_class_id": int(product.get("velocity_class_id", 0) or 0),
        "is_promotional": False,
    }

    series = []
    start_date = datetime.now().date()
    festival_calendar = loader.load_festival_calendar()
    climate_profiles = loader.load_location_climate_profile()
    timeline_dates = _build_timeline_dates_with_festivals(start_date, horizon, festival_calendar, location_id)

    for current_date in timeline_dates:
        ctx = _find_weather_festival_context(loader, product_id, location_id, current_date)
        festival_ctx = _find_festival_calendar_context(festival_calendar, location_id, current_date)
        climate_profile = _find_location_climate_profile(climate_profiles, location_id)

        timeline_payload = {
            **payload,
            "date": current_date.isoformat(),
            **ctx,
        }
        if festival_ctx.get("festival_calendar_status") == "active":
            timeline_payload["is_festival_day"] = True
            timeline_payload["festival_proximity_score"] = 1.0
            timeline_payload["festival_demand_lift_pct"] = festival_ctx.get("festival_calendar_demand_lift_pct", 0.0)
        elif festival_ctx.get("festival_calendar_status") == "proximity":
            timeline_payload["festival_proximity_score"] = festival_ctx.get("festival_calendar_proximity_score", 0.0)
            timeline_payload["festival_demand_lift_pct"] = festival_ctx.get("festival_calendar_demand_lift_pct", 0.0)

        result = svc.predict_single(timeline_payload, horizon=1)
        events = _resolve_timeline_events(ctx, festival_ctx, climate_profile, current_date)
        event_type = events[0]["event_type"] if events else ""
        event_detail = events[0]["event_detail"] if events else ""

        series.append(
            {
                "date": current_date.isoformat(),
                "forecast": round(result.get("predicted_demand", 0), 2),
                "confidence": round(result.get("confidence_score", 90.0), 2),
                "event_type": event_type,
                "event_detail": event_detail,
                "event_types": [event.get("event_type") for event in events],
                "event_details": [event.get("event_detail") for event in events],
            }
        )

    return JSONResponse(
        content={
            "product": {
                "id": product_id,
                "name": product.get("product_name") or product.get("product_code"),
                "category_id": int(product.get("category_id", 0) or 0),
                "velocity_class": product.get("velocity_class"),
                "unit_cost": float(product.get("unit_cost", 0) or 0),
                "unit_price": float(product.get("unit_price", 0) or 0),
                "avg_retail_price": float(product.get("avg_retail_price", 0) or 0),
                "annual_units_max": int(product.get("annual_units_max", 10000) or 10000),
            },
            "location": {"id": location_id, "name": location.get("location_name") or location.get("city")},
            "warehouse": {"id": warehouse_id, "name": warehouse.get("dc_name") if warehouse else None},
            "inventory": {
                "on_hand_qty": getattr(matching_position, "on_hand_qty", 0) if matching_position else 0,
                "allocated_qty": getattr(matching_position, "allocated_qty", 0) if matching_position else 0,
                "available_qty": max(0, (getattr(matching_position, "on_hand_qty", 0) if matching_position else 0) - (getattr(matching_position, "allocated_qty", 0) if matching_position else 0)),
                "safety_stock_qty": getattr(matching_position, "safety_stock_qty", 0) if matching_position else 0,
                "reorder_point_qty": getattr(matching_position, "reorder_point_qty", 0) if matching_position else 0,
                "last_counted_date": getattr(matching_position, "last_counted_date", None) if matching_position else None,
                "in_transit_qty": in_transit_qty,
            },
            "selected_horizon": horizon,
            "series": series,
        }
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
        if payload.get("date"):
            try:
                target_date = datetime.fromisoformat(str(payload["date"])).date()
            except Exception:
                target_date = datetime.now().date()
            loader = CsvInventoryDataLoader()
            festival_calendar = loader.load_festival_calendar()
            festival_ctx = _find_festival_calendar_context(festival_calendar, request.location_id, target_date)
            if festival_ctx.get("festival_calendar_status") == "active":
                payload["is_festival_day"] = True
                payload["festival_proximity_score"] = 1.0
                payload["festival_demand_lift_pct"] = festival_ctx.get("festival_calendar_demand_lift_pct", 0.0)
            elif festival_ctx.get("festival_calendar_status") == "proximity":
                payload["festival_proximity_score"] = festival_ctx.get("festival_calendar_proximity_score", 0.0)
                payload["festival_demand_lift_pct"] = festival_ctx.get("festival_calendar_demand_lift_pct", 0.0)

        result = svc.predict_single(payload, horizon=horizon)

        # Resolve event context for the target date and include in response
        loader = CsvInventoryDataLoader()
        target_date = _parse_optional_date(payload.get("date")) or datetime.now().date()
        ctx = _find_weather_festival_context(loader, request.product_id, request.location_id, target_date)
        festival_calendar = loader.load_festival_calendar()
        festival_ctx = _find_festival_calendar_context(festival_calendar, request.location_id, target_date)
        climate_profiles = loader.load_location_climate_profile()
        climate_profile = _find_location_climate_profile(climate_profiles, request.location_id)
        events = _resolve_timeline_events(ctx, festival_ctx, climate_profile, target_date)
        event_type = events[0]["event_type"] if events else ""
        event_detail = events[0]["event_detail"] if events else ""

        data = PredictData(
            product_id=request.product_id,
            location_id=request.location_id,
            predicted_demand=result["predicted_demand"],
            confidence_score=result["confidence_score"],
            prediction_interval=PredictionInterval(**result["prediction_interval"]),
            model_used=result["model_used"],
            horizon_days=result["horizon_days"],
            latency_ms=result["latency_ms"],
            event_type=event_type,
            event_detail=event_detail,
            event_types=[e.get("event_type") for e in events],
            event_details=[e.get("event_detail") for e in events],
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

        # Enrich each prediction with resolved event context
        loader = CsvInventoryDataLoader()
        festival_calendar = loader.load_festival_calendar()
        climate_profiles = loader.load_location_climate_profile()

        items_out = []
        for i, p in enumerate(predictions):
            row = rows[i] if i < len(rows) else {}
            target_date = _parse_optional_date(row.get("date")) or datetime.now().date()
            ctx = _find_weather_festival_context(loader, row.get("product_id"), row.get("location_id"), target_date)
            festival_ctx = _find_festival_calendar_context(festival_calendar, row.get("location_id"), target_date)
            climate_profile = _find_location_climate_profile(climate_profiles, row.get("location_id"))
            events = _resolve_timeline_events(ctx, festival_ctx, climate_profile, target_date)
            event_type = events[0]["event_type"] if events else ""
            event_detail = events[0]["event_detail"] if events else ""

            items_out.append(
                BatchPredictResultItem(
                    index=p["index"],
                    product_id=p["product_id"],
                    location_id=p["location_id"],
                    predicted_demand=p["predicted_demand"],
                    confidence_score=p["confidence_score"],
                    prediction_interval=PredictionInterval(**p["prediction_interval"]),
                    model_used=p["model_used"],
                    latency_ms=p["latency_ms"],
                    event_type=event_type,
                    event_detail=event_detail,
                )
            )

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

        # Resolve event context for each forecast day
        loader = CsvInventoryDataLoader()
        festival_calendar = loader.load_festival_calendar()
        climate_profiles = loader.load_location_climate_profile()

        forecast_items = []
        for d in forecast_days:
            target_date = _parse_optional_date(d.get("date")) or datetime.now().date()
            ctx = _find_weather_festival_context(loader, product_id, request.location_id, target_date)
            festival_ctx = _find_festival_calendar_context(festival_calendar, request.location_id, target_date)
            climate_profile = _find_location_climate_profile(climate_profiles, request.location_id)
            events = _resolve_timeline_events(ctx, festival_ctx, climate_profile, target_date)
            event_type = events[0]["event_type"] if events else ""
            event_detail = events[0]["event_detail"] if events else ""

            forecast_items.append(
                ForecastDayResult(
                    date=d["date"],
                    forecasted_demand=d["forecasted_demand"],
                    confidence=d["confidence"],
                    prediction_interval=PredictionInterval(**d["prediction_interval"]),
                    trend=d["trend"],
                    seasonality=d["seasonality"],
                    event_type=event_type,
                    event_detail=event_detail,
                )
            )

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
            days_until_stockout=result["days_until_stockout"],
            days_until_reorder=result["days_until_reorder"],
            optimal_reorder_date=result.get("optimal_reorder_date"),
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
