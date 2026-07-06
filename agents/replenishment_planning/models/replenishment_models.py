"""Data models for the Replenishment Planning Agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SupplierInfo:
    """Supplier information from DB4."""
    supplier_id: int
    supplier_name: str
    sku_id: int
    unit_cost: float
    lead_time_days: int
    min_order_qty: int
    reliability_score: float


@dataclass
class ReplenishmentOrder:
    """Replenishment order generated for a SKU-Location pair."""
    order_id: str
    sku_id: int
    location_id: int
    current_stock: int
    reorder_point: int
    safety_stock: int
    order_quantity: int
    unit_cost: float
    total_cost: float
    supplier_id: int
    supplier_name: str
    lead_time_days: int
    order_priority: str  # "URGENT", "HIGH", "MEDIUM", "LOW"
    reasoning: str


@dataclass
class OrderRecommendation:
    """EOQ calculation and order recommendation."""
    sku_id: int
    location_id: int
    annual_demand: int
    holding_cost_per_unit: float
    ordering_cost: float
    eoq: int  # Economic Order Quantity
    reorder_point: int
    is_recommended: bool
    reasoning: str


@dataclass
class ReplenishmentPlanSummary:
    """Summary of replenishment planning results."""
    total_orders_generated: int
    total_order_cost: float
    orders_by_priority: dict[str, int]
    average_lead_time: float
    risky_items_processed: int
    orders: list[ReplenishmentOrder]
