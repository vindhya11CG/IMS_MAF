"""Data models for the Inventory Monitoring Agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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


@dataclass
class WeatherFestivalDemandRecord:
    """Enriched demand context combining inventory, weather, and festival signals."""

    date: str
    sku_id: int
    location_id: int
    category_id: Optional[int] = None
    velocity_class_id: Optional[int] = None
    on_hand_qty: Optional[float] = None
    allocated_qty: Optional[float] = None
    safety_stock_qty: Optional[float] = None
    reorder_point_qty: Optional[float] = None
    daily_demand: Optional[float] = None
    demand_std_dev: Optional[float] = None
    lead_time_days: Optional[float] = None
    supplier_id: Optional[int] = None
    avg_retail_price: Optional[float] = None
    holding_cost_per_unit_day: Optional[float] = None
    handling_cost_per_unit: Optional[float] = None
    order_fulfillment_rate: Optional[float] = None
    total_orders_last_month: Optional[float] = None
    turnover_ratio: Optional[float] = None
    annual_units_max: Optional[float] = None
    season_multiplier: Optional[float] = None
    is_promotional: bool = False
    month: Optional[int] = None
    quarter: Optional[int] = None
    day_of_year: Optional[int] = None
    month_sin: Optional[float] = None
    month_cos: Optional[float] = None
    is_promotional_int: Optional[int] = None
    stock_gap: Optional[float] = None
    available_stock: Optional[float] = None
    safety_ratio: Optional[float] = None
    velocity_score: Optional[float] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    state_province: Optional[str] = None
    city: Optional[str] = None
    climate_zone: Optional[str] = None
    population_index: Optional[float] = None
    income_index: Optional[float] = None
    urbanization_score: Optional[float] = None
    regional_demand_index: Optional[float] = None
    consumer_spending_index: Optional[float] = None
    weather_sensitivity_score: Optional[float] = None
    logistics_complexity_score: Optional[float] = None
    distance_to_dc_km: Optional[float] = None
    regional_supply_risk_score: Optional[float] = None
    market_maturity_index: Optional[float] = None
    temperature_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    rainfall_mm: Optional[float] = None
    snowfall_cm: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    uv_index: Optional[float] = None
    cloud_cover_pct: Optional[float] = None
    pressure_hpa: Optional[float] = None
    visibility_km: Optional[float] = None
    heatwave_flag: bool = False
    coldwave_flag: bool = False
    monsoon_flag: bool = False
    heavy_rain_flag: bool = False
    snowfall_flag: bool = False
    extreme_weather_flag: bool = False
    temperature_deviation: Optional[float] = None
    rainfall_deviation: Optional[float] = None
    weather_severity_index: Optional[float] = None
    weather_demand_multiplier: Optional[float] = None
    weather_supply_risk_score: Optional[float] = None
    climate_anomaly_score: Optional[float] = None
    weather_confidence_score: Optional[float] = None
    weather_adjusted_demand: Optional[float] = None
    regional_adjusted_demand: Optional[float] = None
    weather_adjusted_safety_stock: Optional[float] = None
    weather_adjusted_reorder_point: Optional[float] = None
    demand_volatility_score: Optional[float] = None
    supply_disruption_risk: Optional[float] = None
    stockout_weather_risk: Optional[float] = None
    inventory_weather_pressure: Optional[float] = None
    regional_inventory_risk: Optional[float] = None
    day_of_week: Optional[int] = None
    week_of_year: Optional[int] = None
    season: Optional[str] = None
    forecast_demand_next_7_days: Optional[float] = None
    forecast_demand_next_14_days: Optional[float] = None
    forecast_demand_next_30_days: Optional[float] = None
    is_festival_day: bool = False
    days_to_next_festival: Optional[float] = None
    days_since_last_festival: Optional[float] = None
    festival_proximity_score: Optional[float] = None
    is_shopping_season: bool = False
    daily_demand_pre_festival_adjustment: Optional[float] = None
