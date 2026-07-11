from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SimulationInputItem(BaseModel):
    product_id: int = Field(..., description="Product SKU identifier.", example=1001)
    location_id: int = Field(..., description="Location identifier.", example=7)
    on_hand_qty: int = Field(..., description="Current on-hand stock quantity.", example=120)
    allocated_qty: int = Field(0, description="Quantity already allocated/reserved.", example=20)
    safety_stock_qty: int = Field(..., description="Safety stock threshold.", example=40)
    reorder_point_qty: int = Field(..., description="Reorder point threshold.", example=60)
    demand_multiplier: float = Field(
        1.0,
        description="A multiplier to apply to the forecasted demand for the simulation scenario.",
        example=1.2,
    )


class SimulationRequest(BaseModel):
    items: List[SimulationInputItem] = Field(..., description="Scenario items to simulate.")
    horizon_days: int = Field(..., description="Forecast horizon in days.", example=14)
    description: Optional[str] = Field(None, description="Optional user description of the what-if scenario.")


class SimulationResultItem(BaseModel):
    product_id: int
    location_id: int
    baseline_forecast: int
    scenario_forecast: int
    baseline_projected_stock: int
    scenario_projected_stock: int
    baseline_reorder: float
    scenario_reorder: float
    decision: str
    severity: str


class SimulationResponse(BaseModel):
    scenario: Optional[str]
    horizon_days: int
    items: List[SimulationResultItem]


class FeatureListResponse(BaseModel):
    features: List[str]
    description: str = Field(
        "Model feature list used by the demand forecasting and simulation engine."
    )
