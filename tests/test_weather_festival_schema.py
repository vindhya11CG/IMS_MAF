"""Tests for weather, festival, and regional demand schema integration.

Covers:
  - WeatherFestivalDemandRecord loading via load_weather_festival_dataset()
  - New db6 loaders: load_demand_context_fact(), load_festival_calendar(),
    load_location_climate_profile()
  - build_weather_context_map() result structure and types
  - WeatherFestivalContext model instantiation and helper methods
  - Risk assessment demand scaling with weather context
"""

from __future__ import annotations

import math
from pathlib import Path

# pyrefly: ignore [missing-import]
import pytest

from utils.csv_loader import CsvInventoryDataLoader
from agents.inventory_monitoring.models.inventory_models import (
    WeatherFestivalContext,
    WeatherFestivalDemandRecord,
    RiskAssessment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_loader(tmp_path: Path) -> CsvInventoryDataLoader:
    """CsvInventoryDataLoader rooted at a temp dir with db6 test data."""
    db6 = tmp_path / "db6_csv_export"
    db6.mkdir()

    (db6 / "demand_context_fact.csv").write_text(
        "date,product_id,location_id,temperature_c,humidity_pct,rainfall_mm,"
        "snowfall_cm,heatwave_flag,coldwave_flag,monsoon_flag,heavy_rain_flag,"
        "snowfall_flag,extreme_weather_flag,weather_severity_index,"
        "weather_demand_multiplier,weather_supply_risk_score,climate_anomaly_score,"
        "weather_confidence_score,supply_disruption_risk,stockout_weather_risk,"
        "inventory_weather_pressure,regional_inventory_risk,"
        "is_festival_day,days_to_next_festival,days_since_last_festival,"
        "festival_proximity_score,is_shopping_season,"
        "daily_demand_pre_festival_adjustment,season,day_of_week,week_of_year,"
        "weather_adjusted_demand,regional_adjusted_demand,"
        "weather_adjusted_safety_stock,weather_adjusted_reorder_point,"
        "forecast_demand_next_7_days,forecast_demand_next_14_days,"
        "forecast_demand_next_30_days,regional_demand_index\n"
        "2023-01-05,1,1,17.8,58.0,0.0,0.0,0,0,0,0,0,0,0.12,1.05,0.10,0.08,"
        "0.92,0.10,0.08,0.12,0.11,1,15.0,20.0,0.65,1,38.0,Winter,3,1,"
        "42.0,40.5,12.6,19.0,294.0,588.0,1260.0,1.10\n"
        "2023-03-14,2,3,28.3,85.0,18.7,0.0,0,0,1,1,0,0,0.72,1.35,0.65,0.55,"
        "0.75,0.62,0.58,0.65,0.60,0,3.0,45.0,0.20,1,60.0,Spring,1,11,"
        "81.0,78.0,24.3,35.7,567.0,1134.0,2430.0,1.05\n",
        encoding="utf-8",
    )

    (db6 / "festival_calendar.csv").write_text(
        "festival_id,festival_name,location_id,start_date,end_date,"
        "demand_lift_pct,supply_risk_score,festival_type\n"
        "1,Christmas,1,2023-12-25,2023-12-26,90.0,0.65,NATIONAL\n"
        "2,Black Friday,1,2023-11-24,2023-11-24,80.0,0.55,SHOPPING\n",
        encoding="utf-8",
    )

    (db6 / "location_climate_profile.csv").write_text(
        "location_id,climate_zone,avg_temp_c,avg_rainfall_mm_annual,"
        "weather_sensitivity_score,logistics_complexity_score,regional_demand_index,"
        "population_index,income_index,urbanization_score,consumer_spending_index,"
        "distance_to_dc_km,regional_supply_risk_score,market_maturity_index\n"
        "1,Mediterranean,14.5,508.0,0.35,0.25,1.15,0.95,1.10,0.92,1.08,65.0,0.18,0.88\n"
        "3,Humid-Subtropical,21.2,1250.0,0.58,0.40,1.08,0.88,1.00,0.88,1.02,40.0,0.30,0.85\n",
        encoding="utf-8",
    )

    return CsvInventoryDataLoader(root_dir=tmp_path)


# ---------------------------------------------------------------------------
# Test: original load_weather_festival_dataset (backward compat)
# ---------------------------------------------------------------------------

def test_load_weather_festival_dataset_parses_weather_and_festival_fields(tmp_path: Path) -> None:
    csv_path = tmp_path / "synthetic_inventory_weather_region_v2_festival_demand.csv"
    csv_path.write_text(
        "date,product_id,location_id,temperature_c,humidity_pct,weather_severity_index,"
        "is_festival_day,days_to_next_festival,festival_proximity_score,is_shopping_season\n"
        "2023-01-05,1218,3,17.8,58.0,0.23,1,11.0,0.65,1\n",
        encoding="utf-8",
    )

    loader = CsvInventoryDataLoader(root_dir=tmp_path)
    rows = loader.load_weather_festival_dataset("synthetic_inventory_weather_region_v2_festival_demand.csv")

    assert len(rows) == 1
    assert rows[0].temperature_c == 17.8
    assert rows[0].humidity_pct == 58.0
    assert rows[0].weather_severity_index == 0.23
    assert rows[0].is_festival_day is True
    assert rows[0].days_to_next_festival == 11.0
    assert rows[0].festival_proximity_score == 0.65
    assert rows[0].is_shopping_season is True


# ---------------------------------------------------------------------------
# Test: load_demand_context_fact()
# ---------------------------------------------------------------------------

def test_load_demand_context_fact_returns_records(tmp_loader: CsvInventoryDataLoader) -> None:
    rows = tmp_loader.load_demand_context_fact()
    assert len(rows) == 2
    row = rows[0]
    assert row["product_id"] == 1
    assert row["location_id"] == 1
    assert row["temperature_c"] == pytest.approx(17.8)
    assert row["weather_demand_multiplier"] == pytest.approx(1.05)
    assert row["is_festival_day"] is True
    assert row["is_shopping_season"] is True
    assert row["festival_proximity_score"] == pytest.approx(0.65)
    assert row["regional_demand_index"] == pytest.approx(1.10)


def test_load_demand_context_fact_second_row(tmp_loader: CsvInventoryDataLoader) -> None:
    rows = tmp_loader.load_demand_context_fact()
    row = rows[1]
    assert row["product_id"] == 2
    assert row["location_id"] == 3
    assert row["monsoon_flag"] is True
    assert row["weather_severity_index"] == pytest.approx(0.72)
    assert row["is_festival_day"] is False


# ---------------------------------------------------------------------------
# Test: load_festival_calendar()
# ---------------------------------------------------------------------------

def test_load_festival_calendar_returns_records(tmp_loader: CsvInventoryDataLoader) -> None:
    festivals = tmp_loader.load_festival_calendar()
    assert len(festivals) == 2
    christmas = next(f for f in festivals if f["festival_name"] == "Christmas")
    assert christmas["location_id"] == 1
    assert christmas["demand_lift_pct"] == pytest.approx(90.0)
    assert christmas["supply_risk_score"] == pytest.approx(0.65)
    assert christmas["festival_type"] == "NATIONAL"


# ---------------------------------------------------------------------------
# Test: load_location_climate_profile()
# ---------------------------------------------------------------------------

def test_load_location_climate_profile_returns_records(tmp_loader: CsvInventoryDataLoader) -> None:
    profiles = tmp_loader.load_location_climate_profile()
    assert len(profiles) == 2
    loc1 = next(p for p in profiles if p["location_id"] == 1)
    assert loc1["climate_zone"] == "Mediterranean"
    assert loc1["regional_demand_index"] == pytest.approx(1.15)
    assert loc1["weather_sensitivity_score"] == pytest.approx(0.35)


# ---------------------------------------------------------------------------
# Test: build_weather_context_map()
# ---------------------------------------------------------------------------

def test_build_weather_context_map_returns_dict(tmp_loader: CsvInventoryDataLoader) -> None:
    ctx_map = tmp_loader.build_weather_context_map(source="db6")
    assert isinstance(ctx_map, dict)
    assert len(ctx_map) == 2


def test_build_weather_context_map_keys_are_sku_location_tuples(tmp_loader: CsvInventoryDataLoader) -> None:
    ctx_map = tmp_loader.build_weather_context_map(source="db6")
    for key in ctx_map:
        assert isinstance(key, tuple)
        assert len(key) == 2


def test_build_weather_context_map_values_are_weather_festival_context(tmp_loader: CsvInventoryDataLoader) -> None:
    ctx_map = tmp_loader.build_weather_context_map(source="db6")
    for val in ctx_map.values():
        assert isinstance(val, WeatherFestivalContext)


def test_build_weather_context_map_correct_multiplier(tmp_loader: CsvInventoryDataLoader) -> None:
    ctx_map = tmp_loader.build_weather_context_map(source="db6")
    ctx = ctx_map[(1, 1)]
    assert ctx.weather_demand_multiplier == pytest.approx(1.05)
    assert ctx.is_festival_day is True
    assert ctx.is_shopping_season is True


# ---------------------------------------------------------------------------
# Test: WeatherFestivalContext model methods
# ---------------------------------------------------------------------------

def test_weather_festival_context_defaults_are_neutral() -> None:
    ctx = WeatherFestivalContext()
    assert ctx.weather_demand_multiplier == 1.0
    assert ctx.weather_severity_index == 0.0
    assert ctx.supply_disruption_risk == 0.0
    assert ctx.is_festival_day is False
    assert ctx.is_high_risk() is False


def test_weather_festival_context_is_high_risk_on_extreme_weather() -> None:
    ctx = WeatherFestivalContext(extreme_weather_flag=True)
    assert ctx.is_high_risk() is True


def test_weather_festival_context_is_high_risk_on_high_severity() -> None:
    ctx = WeatherFestivalContext(weather_severity_index=0.75)
    assert ctx.is_high_risk() is True


def test_weather_festival_context_is_high_risk_on_festival_proximity() -> None:
    ctx = WeatherFestivalContext(is_festival_day=True, festival_proximity_score=0.85)
    assert ctx.is_high_risk() is True


def test_weather_festival_context_effective_multiplier_festival_boost() -> None:
    ctx = WeatherFestivalContext(
        weather_demand_multiplier=1.2,
        is_festival_day=True,
        festival_proximity_score=0.9,
    )
    effective = ctx.effective_demand_multiplier()
    # Expected: 1.2 * (1 + 0.9 * 0.3) = 1.2 * 1.27 = 1.524
    assert effective > 1.2
    assert effective <= 2.5  # cap respected


def test_weather_festival_context_effective_multiplier_cap() -> None:
    ctx = WeatherFestivalContext(
        weather_demand_multiplier=2.0,
        is_festival_day=True,
        festival_proximity_score=1.0,
    )
    assert ctx.effective_demand_multiplier() == pytest.approx(2.5)


def test_weather_festival_context_describe_risks_extreme_weather() -> None:
    ctx = WeatherFestivalContext(extreme_weather_flag=True, supply_disruption_risk=0.8)
    reasons = ctx.describe_risks()
    assert any("Extreme weather" in r for r in reasons)
    assert any("Supply disruption" in r or "supply disruption" in r for r in reasons)


def test_weather_festival_context_describe_risks_festival() -> None:
    ctx = WeatherFestivalContext(is_festival_day=True, festival_proximity_score=0.9)
    reasons = ctx.describe_risks()
    assert any("Festival day" in r or "festival" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# Test: RiskAssessment demand scaling with weather context
# ---------------------------------------------------------------------------

def test_risk_assessment_with_high_weather_multiplier_increases_forecast() -> None:
    """Risk monitoring service should scale forecasted demand by weather multiplier."""
    from agents.inventory_monitoring.services.risk_monitoring_service import (
        InventoryRiskMonitoringService,
    )
    from agents.inventory_monitoring.models import InventoryPosition, InventoryCalculationResult

    service = InventoryRiskMonitoringService()

    positions = [
        InventoryPosition(
            position_id=1, sku_id=1, location_id=1,
            on_hand_qty=50, safety_stock_qty=10,
            reorder_point_qty=20, allocated_qty=5,
            last_counted_date=None,
        )
    ]
    calc_results = [
        InventoryCalculationResult(
            sku_id=1, location_id=1, current_stock=50, previous_stock=60,
            sales=10, incoming_stock=0, adjustments=0, source="test",
        )
    ]
    base_demand = {(1, 1): 20}

    # Without weather context
    assessments_no_wx = service.assess_risk(positions, calc_results, [], base_demand)
    base_forecast = assessments_no_wx[0].forecasted_demand

    # With weather context (multiplier=1.5)
    wx_map = {(1, 1): WeatherFestivalContext(weather_demand_multiplier=1.5)}
    assessments_wx = service.assess_risk(positions, calc_results, [], base_demand, weather_context_map=wx_map)
    wx_forecast = assessments_wx[0].forecasted_demand

    assert wx_forecast > base_forecast
    expected = math.ceil(20 * 1.5)
    assert wx_forecast == expected, f"Expected {expected}, got {wx_forecast}"


def test_risk_assessment_weather_context_attached_to_result() -> None:
    """Weather context should be propagated onto the RiskAssessment."""
    from agents.inventory_monitoring.services.risk_monitoring_service import (
        InventoryRiskMonitoringService,
    )
    from agents.inventory_monitoring.models import InventoryPosition, InventoryCalculationResult

    service = InventoryRiskMonitoringService()
    positions = [
        InventoryPosition(
            position_id=1, sku_id=5, location_id=2,
            on_hand_qty=100, safety_stock_qty=15,
            reorder_point_qty=30, allocated_qty=10,
            last_counted_date=None,
        )
    ]
    calc_results = [
        InventoryCalculationResult(
            sku_id=5, location_id=2, current_stock=100, previous_stock=110,
            sales=10, incoming_stock=0, adjustments=0, source="test",
        )
    ]
    wx_ctx = WeatherFestivalContext(weather_demand_multiplier=1.2, is_festival_day=True)
    wx_map = {(5, 2): wx_ctx}
    assessments = service.assess_risk(positions, calc_results, [], {(5, 2): 30}, weather_context_map=wx_map)

    assert assessments[0].weather_context is not None
    assert assessments[0].weather_context.is_festival_day is True
    assert assessments[0].weather_context.weather_demand_multiplier == pytest.approx(1.2)


def test_risk_assessment_no_weather_context_backward_compat() -> None:
    """Calling assess_risk without weather_context_map must behave identically to before."""
    from agents.inventory_monitoring.services.risk_monitoring_service import (
        InventoryRiskMonitoringService,
    )
    from agents.inventory_monitoring.models import InventoryPosition, InventoryCalculationResult

    service = InventoryRiskMonitoringService()
    positions = [
        InventoryPosition(
            position_id=1, sku_id=7, location_id=3,
            on_hand_qty=5, safety_stock_qty=10,
            reorder_point_qty=20, allocated_qty=0,
            last_counted_date=None,
        )
    ]
    calc_results = [
        InventoryCalculationResult(
            sku_id=7, location_id=3, current_stock=5, previous_stock=15,
            sales=10, incoming_stock=0, adjustments=0, source="test",
        )
    ]
    assessments = service.assess_risk(positions, calc_results, [], {(7, 3): 15})

    assert assessments[0].weather_context is None
    assert assessments[0].risk_detected is True  # stock below reorder & safety
