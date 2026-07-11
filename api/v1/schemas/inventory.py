from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class InventoryReorderItem(BaseModel):
    product_id: int = Field(..., description="Product SKU identifier.", example=1001)
    location_id: int = Field(..., description="Location identifier.", example=7)
    on_hand_qty: int = Field(..., description="Current on-hand stock quantity.", example=120)
    allocated_qty: int = Field(0, description="Quantity already allocated/reserved.", example=20)
    safety_stock_qty: int = Field(..., description="Safety stock threshold.", example=40)
    reorder_point_qty: int = Field(..., description="Reorder point threshold.", example=60)
    in_transit_qty: int = Field(0, description="Quantity already in transit to this location.", example=10)
    forecasted_demand: Optional[int] = Field(
        None,
        description="Optional demand forecast. If omitted, the model will estimate demand.",
        example=35,
    )


class InventoryReorderRequest(BaseModel):
    items: List[InventoryReorderItem] = Field(
        ..., description="The inventory items to evaluate for reorder recommendations."
    )


class InventoryReorderResponseItem(BaseModel):
    product_id: int
    location_id: int
    forecasted_demand: int
    available_stock: int
    projected_stock: int
    decision: str
    severity: str
    recommended_reorder: float
    recommended_action: str


class InventoryReorderResponse(BaseModel):
    items: List[InventoryReorderResponseItem]


class InventoryRiskItem(BaseModel):
    product_id: int = Field(..., description="Product SKU identifier.", example=1001)
    location_id: int = Field(..., description="Location identifier.", example=7)
    current_stock: int = Field(..., description="Current on-hand stock quantity.", example=120)
    safety_stock_qty: int = Field(..., description="Safety stock threshold.", example=40)
    reorder_point_qty: int = Field(..., description="Reorder point threshold.", example=60)
    in_transit_qty: int = Field(0, description="Quantity already in transit.", example=10)
    forecasted_demand: int = Field(0, description="Forecasted demand for the evaluation horizon.", example=35)
    allocated_qty: int = Field(0, description="Quantity already allocated or reserved.", example=20)


class InventoryRiskRequest(BaseModel):
    items: Optional[List[InventoryRiskItem]] = Field(
        None,
        description="Inventory positions to score. When omitted, the endpoint can use CSV-backed defaults if configured.",
    )
    risk_horizon_days: int = Field(
        14,
        description="The forecast horizon in days used to interpret demand and risk exposure.",
        example=14,
    )


class InventoryRiskResponseItem(BaseModel):
    product_id: int
    location_id: int
    current_stock: int
    safety_stock_qty: int
    reorder_point_qty: int
    forecasted_demand: int
    projected_stock: int
    risk_detected: bool
    risk_score: float
    risk_reasons: List[str]
    recommended_action: str


class InventoryRiskResponse(BaseModel):
    items: List[InventoryRiskResponseItem]
