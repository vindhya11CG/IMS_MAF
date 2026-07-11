from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from api.v1.schemas.simulation import (
    FeatureListResponse,
    SimulationRequest,
    SimulationResponse,
)
from demand_forecast_agent.services.feature_engineering_service import FeatureEngineeringService
from demand_forecast_agent.services.core_forecasting_service import ForecastService
from demand_forecast_agent.services.decision_services import (
    InventoryDecisionService,
    ReorderService,
)

router = APIRouter()


@router.get(
    "/features",
    response_model=FeatureListResponse,
    summary="Retrieve the model feature list used by the forecasting engine",
    description=(
        "Returns the exact ordered feature list that the demand forecasting "
        "engine expects for model inference and scenario simulation."
    ),
)
async def get_feature_list() -> FeatureListResponse:
    return FeatureListResponse(
        features=FeatureEngineeringService.MODEL_FEATURES,
    )


@router.post(
    "/simulate",
    response_model=SimulationResponse,
    summary="Run a what-if inventory demand and reorder simulation",
    description=(
        "Simulates a demand multiplier scenario for inventory positions, "
        "returning baseline vs scenario forecasts, projected stock, and "
        "recommended reorder quantities."
    ),
)
async def simulate_scenario(request: SimulationRequest) -> SimulationResponse:
    forecast_service = ForecastService()
    decision_service = InventoryDecisionService()
    reorder_service = ReorderService()

    results: List[dict] = []

    for item in request.items:
        payload = {
            "product_id": item.product_id,
            "location_id": item.location_id,
            "on_hand_qty": item.on_hand_qty,
            "allocated_qty": item.allocated_qty,
            "safety_stock_qty": item.safety_stock_qty,
            "reorder_point_qty": item.reorder_point_qty,
            "date": None,
            "is_promotional": False,
            "annual_units_max": 0,
            "avg_retail_price": 0.0,
            "holding_cost_per_unit_day": 0.0,
            "handling_cost_per_unit": 0.0,
            "order_fulfillment_rate": 0.0,
            "total_orders_last_month": 0,
            "turnover_ratio": 0.0,
            "demand_std_dev": 0.0,
            "lead_time_days": 0,
            "season_multiplier": 1.0,
            "category_id": 0,
            "velocity_class_id": 0,
        }

        engineered = FeatureEngineeringService().execute(payload)
        baseline_result = forecast_service.execute(
            engineered,
            horizon=request.horizon_days,
            product_id=item.product_id,
        )

        if baseline_result["status"] != "SUCCESS":
            raise HTTPException(
                status_code=500,
                detail=baseline_result.get("message", "Unable to compute baseline forecast."),
            )

        baseline_forecast = int(round(baseline_result["forecast"]))
        scenario_forecast = int(round(baseline_forecast * item.demand_multiplier))

        baseline_decision = decision_service.execute(
            baseline_forecast,
            item.on_hand_qty,
            item.reorder_point_qty,
            item.safety_stock_qty,
        )
        scenario_decision = decision_service.execute(
            scenario_forecast,
            item.on_hand_qty,
            item.reorder_point_qty,
            item.safety_stock_qty,
        )

        baseline_reorder = reorder_service.execute(
            baseline_forecast,
            item.on_hand_qty,
            item.allocated_qty,
            item.safety_stock_qty,
        )
        scenario_reorder = reorder_service.execute(
            scenario_forecast,
            item.on_hand_qty,
            item.allocated_qty,
            item.safety_stock_qty,
        )

        results.append(
            {
                "product_id": item.product_id,
                "location_id": item.location_id,
                "baseline_forecast": baseline_forecast,
                "scenario_forecast": scenario_forecast,
                "baseline_projected_stock": item.on_hand_qty - baseline_forecast,
                "scenario_projected_stock": item.on_hand_qty - scenario_forecast,
                "baseline_reorder": baseline_reorder,
                "scenario_reorder": scenario_reorder,
                "decision": scenario_decision["decision"],
                "severity": scenario_decision["severity"],
            }
        )

    return SimulationResponse(
        scenario=request.description,
        horizon_days=request.horizon_days,
        items=[
            {
                "product_id": row["product_id"],
                "location_id": row["location_id"],
                "baseline_forecast": row["baseline_forecast"],
                "scenario_forecast": row["scenario_forecast"],
                "baseline_projected_stock": row["baseline_projected_stock"],
                "scenario_projected_stock": row["scenario_projected_stock"],
                "baseline_reorder": row["baseline_reorder"],
                "scenario_reorder": row["scenario_reorder"],
                "decision": row["decision"],
                "severity": row["severity"],
            }
            for row in results
        ],
    )
