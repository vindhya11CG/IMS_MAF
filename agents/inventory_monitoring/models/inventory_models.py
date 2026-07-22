"""Data models for the Inventory Monitoring Agent.

Extended in Phase 6 to include:
- WeatherFestivalContext: lightweight weather/festival context carrier propagated
  through the pipeline without coupling downstream agents to the full
  WeatherFestivalDemandRecord (which is loading-time only).
- RiskAssessment.weather_context: optional field added with default=None so
  existing callsites remain fully backward-compatible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


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
class WeatherFestivalContext:
    """Lightweight context object carrying weather and festival signals.

    This is the pipeline-internal representation of weather/festival state
    for a given (sku_id, location_id) pair. It is populated from
    WeatherFestivalDemandRecord at load time and propagated downstream
    so agents can act on weather/festival signals without re-loading the
    full dataset.

    All numeric fields default to neutral/safe values so the object is safe
    to instantiate with partial data — downstream logic that checks
    weather_demand_multiplier will receive 1.0 (no adjustment) if the field
    was absent in the source dataset.
    """

    # Weather multipliers and risk scores
    weather_demand_multiplier: float = 1.0
    weather_severity_index: float = 0.0
    weather_supply_risk_score: float = 0.0
    climate_anomaly_score: float = 0.0
    weather_confidence_score: float = 1.0
    supply_disruption_risk: float = 0.0
    stockout_weather_risk: float = 0.0
    inventory_weather_pressure: float = 0.0
    regional_inventory_risk: float = 0.0

    # Weather condition flags
    heatwave_flag: bool = False
    coldwave_flag: bool = False
    monsoon_flag: bool = False
    heavy_rain_flag: bool = False
    snowfall_flag: bool = False
    extreme_weather_flag: bool = False

    # Key weather observations
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    rainfall_mm: Optional[float] = None
    snowfall_cm: Optional[float] = None

    # Adjusted demand signals
    weather_adjusted_demand: Optional[float] = None
    weather_adjusted_safety_stock: Optional[float] = None
    weather_adjusted_reorder_point: Optional[float] = None

    # Festival signals
    is_festival_day: bool = False
    days_to_next_festival: Optional[float] = None
    festival_proximity_score: float = 0.0
    is_shopping_season: bool = False
    daily_demand_pre_festival_adjustment: Optional[float] = None

    # Regional demand
    regional_demand_index: float = 1.0
    regional_adjusted_demand: Optional[float] = None

    # Season metadata
    season: Optional[str] = None

    def is_high_risk(self) -> bool:
        """Return True if this context indicates elevated supply or demand risk."""
        return (
            self.weather_severity_index > 0.6
            or self.supply_disruption_risk > 0.5
            or self.extreme_weather_flag
            or (self.is_festival_day and self.festival_proximity_score > 0.7)
        )

    def effective_demand_multiplier(self) -> float:
        """Return the effective demand multiplier combining weather and festival signals.

        Festival proximity further amplifies demand on top of the weather multiplier.
        Both effects are capped to avoid runaway order quantities.
        """
        festival_boost = 1.0 + (self.festival_proximity_score * 0.3 if self.is_festival_day else 0.0)
        combined = self.weather_demand_multiplier * festival_boost
        return min(combined, 2.5)  # cap at 2.5× to prevent runaway orders

    def describe_risks(self) -> List[str]:
        """Return human-readable risk reason strings for this context."""
        reasons: List[str] = []
        if self.extreme_weather_flag:
            reasons.append("Extreme weather event active — supply disruption risk elevated.")
        if self.heatwave_flag:
            reasons.append("Heatwave conditions — demand for cooling/beverage products elevated.")
        if self.coldwave_flag:
            reasons.append("Cold wave conditions — demand for heating/winter products elevated.")
        if self.monsoon_flag:
            reasons.append("Monsoon conditions — logistics complexity and supply risk elevated.")
        if self.snowfall_flag:
            reasons.append("Heavy snowfall — last-mile delivery risk elevated.")
        if self.heavy_rain_flag:
            reasons.append("Heavy rain — store foot traffic suppressed, online demand may spike.")
        if self.weather_severity_index > 0.6:
            reasons.append(
                f"Weather severity index {self.weather_severity_index:.2f} exceeds high-risk threshold (0.60)."
            )
        if self.supply_disruption_risk > 0.5:
            reasons.append(
                f"Supply disruption risk {self.supply_disruption_risk:.2f} exceeds moderate-risk threshold (0.50)."
            )
        if self.is_festival_day:
            reasons.append(
                f"Festival day — proximity score {self.festival_proximity_score:.2f}, "
                f"demand lift expected (multiplier: {self.effective_demand_multiplier():.2f}×)."
            )
        elif self.is_shopping_season:
            reasons.append("Active shopping season — sustained above-baseline demand expected.")
        return reasons


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
    # Optional weather/festival context — None means not yet enriched.
    # Downstream agents must treat None as "no weather context available"
    # and fall back to default behaviour (neutral multipliers, no weather risk).
    weather_context: Optional[WeatherFestivalContext] = None


@dataclass
class WeatherFestivalDemandRecord:
    """Enriched demand context combining inventory, weather, and festival signals.

    This is the full record loaded from
    synthetic_inventory_weather_region_v2_festival_demand.csv
    (or its synthetic equivalent in data/csv_exports/db6_csv_export/).

    At pipeline runtime this record is converted to the lighter-weight
    WeatherFestivalContext before being attached to RiskAssessment objects,
    so downstream agents never need to import or handle this class directly.
    """

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

    def to_weather_festival_context(self) -> WeatherFestivalContext:
        """Convert this full record to the lightweight pipeline context object."""
        return WeatherFestivalContext(
            weather_demand_multiplier=self.weather_demand_multiplier or 1.0,
            weather_severity_index=self.weather_severity_index or 0.0,
            weather_supply_risk_score=self.weather_supply_risk_score or 0.0,
            climate_anomaly_score=self.climate_anomaly_score or 0.0,
            weather_confidence_score=self.weather_confidence_score or 1.0,
            supply_disruption_risk=self.supply_disruption_risk or 0.0,
            stockout_weather_risk=self.stockout_weather_risk or 0.0,
            inventory_weather_pressure=self.inventory_weather_pressure or 0.0,
            regional_inventory_risk=self.regional_inventory_risk or 0.0,
            heatwave_flag=self.heatwave_flag,
            coldwave_flag=self.coldwave_flag,
            monsoon_flag=self.monsoon_flag,
            heavy_rain_flag=self.heavy_rain_flag,
            snowfall_flag=self.snowfall_flag,
            extreme_weather_flag=self.extreme_weather_flag,
            temperature_c=self.temperature_c,
            humidity_pct=self.humidity_pct,
            rainfall_mm=self.rainfall_mm,
            snowfall_cm=self.snowfall_cm,
            weather_adjusted_demand=self.weather_adjusted_demand,
            weather_adjusted_safety_stock=self.weather_adjusted_safety_stock,
            weather_adjusted_reorder_point=self.weather_adjusted_reorder_point,
            is_festival_day=self.is_festival_day,
            days_to_next_festival=self.days_to_next_festival,
            festival_proximity_score=self.festival_proximity_score or 0.0,
            is_shopping_season=self.is_shopping_season,
            daily_demand_pre_festival_adjustment=self.daily_demand_pre_festival_adjustment,
            regional_demand_index=self.regional_demand_index or 1.0,
            regional_adjusted_demand=self.regional_adjusted_demand,
            season=self.season,
        )
