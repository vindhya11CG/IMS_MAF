from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

@dataclass
class InventoryEvent:
    event_id: int
    event_type: str
    sku_id: int
    location_id: int
    quantity_change: int
    event_timestamp: str
    reference_id: str
    source_location_id: Optional[int]
    destination_location_id: Optional[int]
    event_reason: str
    created_by: str

@dataclass
class InventoryPosition:
    position_id: int
    sku_id: int
    location_id: int
    on_hand_qty: int
    safety_stock_qty: int
    reorder_point_qty: int
    allocated_qty: int
    last_counted_date: Optional[str]

@dataclass
class InventorySnapshot:
    snapshot_id: int
    snapshot_date: str
    sku_id: int
    location_id: int
    opening_stock: int
    receipts: int
    sales: int
    transfers_in: int
    transfers_out: int
    adjustments: int
    closing_stock: int

@dataclass
class InventoryCalculationResult:
    sku_id: int
    location_id: int
    current_stock: int
    previous_stock: int
    sales: int
    incoming_stock: int
    adjustments: int
    source: str

@dataclass
class RiskAssessment:
    sku_id: int
    location_id: int
    current_stock: int
    safety_stock: int
    reorder_point: int
    in_transit_qty: int
    forecasted_demand: int
    projected_stock: int
    risk_detected: bool
    risk_reasons: list[str]
    recommended_action: str
