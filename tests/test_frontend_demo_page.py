import logging
from datetime import date

from fastapi.testclient import TestClient

from api.app import app
from api.v1.routers.forecasting import (
    _advance_timeline_date,
    _find_festival_calendar_context,
    _find_location_climate_profile,
    _find_weather_festival_context,
    _resolve_timeline_events,
)
from utils.csv_loader import CsvInventoryDataLoader


def test_frontend_demo_html_is_served():
    client = TestClient(app)

    response = client.get("/api/v1/forecasting/frontend/demo")

    assert response.status_code == 200
    assert "Demand Predictor" in response.text
    assert "Load Graph" in response.text or "Load graph" in response.text


def test_timeline_horizon_advances_from_today():
    today = date(2026, 7, 30)

    assert _advance_timeline_date(today, "1-day") == date(2026, 7, 31)
    assert _advance_timeline_date(today, "7-day") == date(2026, 8, 6)
    assert _advance_timeline_date(today, "30-day") == date(2026, 8, 29)
    assert _advance_timeline_date(date(2026, 1, 31), "monthly") == date(2026, 2, 28)
    assert _advance_timeline_date(date(2026, 12, 31), "yearly") == date(2027, 12, 31)


def test_weather_festival_context_requires_exact_or_nearby_product_date():
    loader = CsvInventoryDataLoader()

    context = _find_weather_festival_context(
        loader,
        product_id=99,
        location_id=1,
        target_date=date(2026, 7, 30),
    )

    assert context == {}, "Expected no stale product-level context for an unknown product"


def test_festival_calendar_context_returns_active_marker_for_known_festival_date():
    loader = CsvInventoryDataLoader()
    festival_calendar = loader.load_festival_calendar()

    context = _find_festival_calendar_context(
        festival_calendar,
        location_id=1,
        target_date=date(2023, 7, 4),
    )

    assert context.get("festival_calendar_status") == "active"
    assert "Independence Day" in context.get("festival_calendar_name", "")


def test_timeline_resolver_can_return_multiple_event_types():
    loader = CsvInventoryDataLoader()
    festival_calendar = loader.load_festival_calendar()
    climate_profile = _find_location_climate_profile(
        loader.load_location_climate_profile(), location_id=1
    )
    festival_ctx = _find_festival_calendar_context(
        festival_calendar,
        location_id=1,
        target_date=date(2023, 9, 2),
    )

    events = _resolve_timeline_events(
        {},
        festival_ctx,
        climate_profile,
        date(2023, 9, 2),
    )

    assert any(event["event_type"] == "festival" for event in events)
    assert any(event["event_type"] == "weekend" for event in events)
    assert len(events) >= 2


def test_timeline_resolver_does_not_emit_generic_festival_or_weather_markers():
    climate_profile = _find_location_climate_profile(
        CsvInventoryDataLoader().load_location_climate_profile(), location_id=1
    )

    events = _resolve_timeline_events(
        {"festival_proximity_score": 0.2, "weather_severity_index": 0.2},
        {},
        climate_profile,
        date(2026, 8, 2),
    )

    assert not any(event["event_type"] == "festival" for event in events)
    assert not any(event["event_type"] == "weather" for event in events)


def test_festival_calendar_context_recurs_annually_for_future_years():
    loader = CsvInventoryDataLoader()
    festival_calendar = loader.load_festival_calendar()

    context = _find_festival_calendar_context(
        festival_calendar,
        location_id=1,
        target_date=date(2026, 7, 4),
    )

    assert context.get("festival_calendar_status") == "active"


def test_weather_context_recurs_annually_for_future_years():
    loader = CsvInventoryDataLoader()

    context = _find_weather_festival_context(
        loader,
        product_id=5,
        location_id=4,
        target_date=date(2026, 6, 21),
    )

    assert context.get("weather_severity_index") is not None


def test_frontend_timeline_graph_includes_product_inventory_details():
    client = TestClient(app)

    response = client.get("/api/v1/forecasting/frontend/timeline-graph?product_id=5&location_id=1&warehouse_id=1&horizon=7-day")
    assert response.status_code == 200
    payload = response.json()

    assert payload["product"]["id"] == 5
    assert "unit_cost" in payload["product"]
    assert "unit_price" in payload["product"]
    assert "inventory" in payload
    assert "on_hand_qty" in payload["inventory"]
    assert "allocated_qty" in payload["inventory"]
    assert "in_transit_qty" in payload["inventory"]


def test_location_climate_profile_supports_weather_risk_events():
    loader = CsvInventoryDataLoader()
    climate_profile = _find_location_climate_profile(
        loader.load_location_climate_profile(), location_id=10
    )

    assert climate_profile
    assert float(str(climate_profile.get("weather_sensitivity_score", 0.0))) >= 0.55
    assert float(str(climate_profile.get("regional_supply_risk_score", 0.0))) >= 0.3


def test_load_distribution_centers_prefers_db1_without_missing_file_warning(caplog):
    caplog.set_level(logging.WARNING, logger="utils.csv_loader")
    loader = CsvInventoryDataLoader()
    dcs = loader.load_distribution_centers()

    assert isinstance(dcs, list)
    assert dcs, "Expected distribution centers to be loaded from db1_csv_export"
    assert not any(
        record.levelname == "WARNING"
        and "CSV file not found" in record.message
        and "distribution_centers.csv" in record.message
        for record in caplog.records
    )
