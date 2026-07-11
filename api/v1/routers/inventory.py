from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException

from api.core.dependencies import get_app_state
from api.core.state import AppState
from api.v1.schemas.inventory import (
    InventoryReorderRequest,
    InventoryReorderResponse,
    InventoryRiskRequest,
    InventoryRiskResponse,
)
from demand_forecast_agent.services.feature_engineering_service import FeatureEngineeringService
from demand_forecast_agent.services.core_forecasting_service import ForecastService
from demand_forecast_agent.services.decision_services import (
    InventoryDecisionService,
    ReorderService,
)
from utils.csv_loader import CsvInventoryDataLoader
from agents.inventory_monitoring.models.inventory_models import (
    InventoryPosition,
    InventorySnapshot,
)
from agents.inventory_monitoring.services.calculation_service import InventoryCalculationService
from agents.inventory_monitoring.services.risk_monitoring_service import InventoryRiskMonitoringService

router = APIRouter()


@router.get("/snapshots")
async def get_snapshots(state: AppState = Depends(get_app_state)):
    """Get all daily inventory snapshots (Agent 1 Input)."""
    return state.raw_data.get("snapshots", [])


@router.get("/positions")
async def get_positions(state: AppState = Depends(get_app_state)):
    """Get all baseline inventory positions (Agent 1 Input)."""
    return state.raw_data.get("positions", [])


def _build_engineering_payload(item: dict) -> dict:
    return {
        "product_id": item["product_id"],
        "location_id": item["location_id"],
        "on_hand_qty": item["on_hand_qty"],
        "allocated_qty": item.get("allocated_qty", 0),
        "safety_stock_qty": item["safety_stock_qty"],
        "reorder_point_qty": item["reorder_point_qty"],
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


@router.post(
    "/reorder",
    response_model=InventoryReorderResponse,
    summary="Generate reorder recommendations for inventory items",
    description=(
        "Evaluates inventory positions and produces reorder recommendations "
        "based on forecasted demand, stock levels, safety stock, and reorder points."
    ),
)
async def reorder_recommendations(
    request: InventoryReorderRequest,
    state: AppState = Depends(get_app_state),
):
    forecast_service = ForecastService()
    decision_service = InventoryDecisionService()
    reorder_service = ReorderService()

    items: List[Dict] = []

    for item in request.items:
        item_data = item.model_dump()
        forecast = item.forecasted_demand

        if forecast is None:
            payload = _build_engineering_payload(item_data)
            engineered = FeatureEngineeringService().execute(payload)
            forecast_response = forecast_service.execute(
                engineered,
                horizon=14,
                product_id=item.product_id,
            )

            if forecast_response["status"] != "SUCCESS":
                raise HTTPException(
                    status_code=500,
                    detail=forecast_response.get("message", "Forecast failed."),
                )

            forecast = int(round(forecast_response["forecast"]))

        available_stock = item.on_hand_qty - item.allocated_qty + item.in_transit_qty
        projected_stock = item.on_hand_qty + item.in_transit_qty - forecast
        decision = decision_service.execute(
            forecast,
            item.on_hand_qty,
            item.reorder_point_qty,
            item.safety_stock_qty,
        )
        recommended_reorder = reorder_service.execute(
            forecast,
            item.on_hand_qty,
            item.allocated_qty,
            item.safety_stock_qty,
            transit=item.in_transit_qty,
        )

        items.append(
            {
                "product_id": item.product_id,
                "location_id": item.location_id,
                "forecasted_demand": forecast,
                "available_stock": available_stock,
                "projected_stock": projected_stock,
                "decision": decision["decision"],
                "severity": decision["severity"],
                "recommended_reorder": recommended_reorder,
                "recommended_action": (
                    "Place replenishment order immediately." if decision["decision"] == "REORDER_IMMEDIATELY" else "Review inventory and monitor closely."
                ),
            }
        )

    return {"items": items}


@router.post(
    "/risk",
    response_model=InventoryRiskResponse,
    summary="Score inventory risk for one or more inventory positions",
    description=(
        "Calculates an inventory risk score and reasons based on current stock, "
        "forecasted demand, safety stock, reorder point, and in-transit inventory."
    ),
)
async def inventory_risk_scoring(
    request: InventoryRiskRequest,
    state: AppState = Depends(get_app_state),
):
    loader = CsvInventoryDataLoader()
    positions: List[InventoryPosition] = []

    if request.items is not None:
        for item in request.items:
            positions.append(
                InventoryPosition(
                    position_id=0,
                    sku_id=item.product_id,
                    location_id=item.location_id,
                    on_hand_qty=item.current_stock,
                    safety_stock_qty=item.safety_stock_qty,
                    reorder_point_qty=item.reorder_point_qty,
                    allocated_qty=item.allocated_qty,
                    last_counted_date=None,
                )
            )
    else:
        positions = loader.load_inventory_positions()

    raw_snapshots = loader.load_inventory_daily_snapshots()
    snapshot_objs: List[InventorySnapshot] = []
    for row in raw_snapshots:
        if not isinstance(row, dict):
            continue
        snapshot_objs.append(
            InventorySnapshot(
                snapshot_id=row.get("snapshot_id", 0),
                snapshot_date=row.get("snapshot_date", ""),
                sku_id=row.get("sku_id", 0),
                location_id=row.get("location_id", 0),
                opening_stock=row.get("opening_stock", 0),
                receipts=row.get("receipts", 0),
                sales=row.get("sales", 0),
                transfers_in=row.get("transfers_in", 0),
                transfers_out=row.get("transfers_out", 0),
                adjustments=row.get("adjustments", 0),
                closing_stock=row.get("closing_stock", 0),
            )
        )

    calculation_service = InventoryCalculationService()
    calculation_results = calculation_service.execute(positions, snapshot_objs)

    risk_service = InventoryRiskMonitoringService()
    forecasted_demand: Dict[Tuple[int, int], int] = {}

    if request.items is not None:
        for item in request.items:
            if item.forecasted_demand is not None:
                forecasted_demand[(item.product_id, item.location_id)] = item.forecasted_demand

    if not forecasted_demand:
        forecasted_demand = risk_service.estimate_forecasted_demand(
            calculation_results,
            lookback_periods=4,
        )

    assessments = risk_service.assess_risk(
        positions,
        calculation_results,
        loader.load_in_transit_inventory(),
        forecasted_demand,
    )

    items: List[Dict] = []
    for assessment in assessments:
        score = min(100.0, 100.0 * len(assessment.risk_reasons) / 3.0)
        items.append(
            {
                "product_id": assessment.sku_id,
                "location_id": assessment.location_id,
                "current_stock": assessment.current_stock,
                "safety_stock_qty": assessment.safety_stock,
                "reorder_point_qty": assessment.reorder_point,
                "forecasted_demand": assessment.forecasted_demand,
                "projected_stock": assessment.projected_stock,
                "risk_detected": assessment.risk_detected,
                "risk_score": round(score, 2),
                "risk_reasons": assessment.risk_reasons,
                "recommended_action": assessment.recommended_action,
            }
        )

    return {"items": items}
