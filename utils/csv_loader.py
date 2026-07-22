from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

from .parsing import parse_bool, parse_float, parse_int, parse_optional_int

if TYPE_CHECKING:
    from agents.inventory_monitoring.models.inventory_models import (
        InventoryPosition,
        WeatherFestivalContext,
        WeatherFestivalDemandRecord,
    )


def parse_optional_float(value: Optional[str | int | float]) -> Optional[float]:
    """Parse a string or numeric value to optional float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    value = value.strip().replace("\ufeff", "")
    if value == "" or value.upper() in {"NULL", "NONE"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None

logger = logging.getLogger(__name__)


class CsvInventoryDataLoader:
    """
    Loads inventory agent data from the csv_exports folder.
    
    Supports 5 database exports:
    - db1_csv_export: Store & warehouse network (50 stores + 3 DCs across 10 states)
    - db2_csv_export: Product master data (5,000 SKUs + categories + seasonality)
    - db3_csv_export: Inventory core (positions + in-transit)
    - db4_csv_export: Supplier data (35 suppliers + pricing + performance)
    - db5_csv_export: Daily operations (snapshots + events)
    """

    def __init__(self, root_dir: str | Path = "data/csv_exports") -> None:
        self.root_dir = Path(root_dir)
        if not self.root_dir.exists():
            alternate_root = self.root_dir.parent
            if alternate_root.exists():
                logger.warning(
                    f"CSV root {self.root_dir} not found, falling back to {alternate_root}"
                )
                self.root_dir = alternate_root

    def _read_rows(self, file_path: Path) -> List[Dict[str, str]]:
        """Read CSV file and return list of dictionaries."""
        if not file_path.exists():
            logger.warning(f"CSV file not found: {file_path}")
            return []

        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                if reader.fieldnames is None:
                    logger.error(f"Empty or invalid CSV file: {file_path}")
                    return []
                    
                rows: List[Dict[str, str]] = []
                for row in reader:
                    normalized = {key.strip().lstrip("\ufeff"): (value or "") for key, value in row.items()}
                    rows.append(normalized)
                    
                logger.info(f"Loaded {len(rows)} rows from {file_path.name}")
                return rows
        except Exception as e:
            logger.error(f"Error reading CSV file {file_path}: {e}")
            return []

    def load_inventory_positions(self) -> List["InventoryPosition"]:
        """Load inventory positions from CSV."""
        from agents.inventory_monitoring.models.inventory_models import InventoryPosition

        rows = self._read_rows(self.root_dir / "db3_csv_export" / "inventory_positions.csv")

        positions: List[InventoryPosition] = []
        for row in rows:
            try:
                position = InventoryPosition(
                    position_id=parse_int(row.get("position_id")),
                    sku_id=parse_int(row.get("sku_id") or row.get("product_id")),
                    location_id=parse_int(row.get("location_id")),
                    on_hand_qty=parse_int(row.get("on_hand_qty")),
                    safety_stock_qty=parse_int(row.get("safety_stock_qty")),
                    reorder_point_qty=parse_int(row.get("reorder_point_qty")),
                    allocated_qty=parse_int(row.get("allocated_qty")),
                    last_counted_date=row.get("last_counted_date", "").strip() or None,
                )
                positions.append(position)
            except Exception as e:
                logger.error(f"Error parsing inventory position row: {e}")
                continue
        return positions

    def load_inventory_daily_snapshots(self) -> List[Dict]:
        """Load inventory daily snapshots from CSV."""
        rows = self._read_rows(self.root_dir / "db5_csv_export" / "inventory_daily_snapshots.csv")
        snapshots = []
        for row in rows:
            try:
                snapshot = {
                    "snapshot_id": parse_int(row.get("snapshot_id")),
                    "snapshot_date": row.get("snapshot_date", "").strip(),
                    "sku_id": parse_int(row.get("sku_id")),
                    "location_id": parse_int(row.get("location_id")),
                    "opening_stock": parse_int(row.get("opening_stock")),
                    "receipts": parse_int(row.get("receipts")),
                    "sales": parse_int(row.get("sales")),
                    "transfers_in": parse_int(row.get("transfers_in")),
                    "transfers_out": parse_int(row.get("transfers_out")),
                    "adjustments": parse_int(row.get("adjustments")),
                    "closing_stock": parse_int(row.get("closing_stock")),
                }
                snapshots.append(snapshot)
            except Exception as e:
                logger.error(f"Error parsing inventory snapshot row: {e}")
                continue
        return snapshots

    def load_weather_festival_dataset(self, file_name: str | Path = "synthetic_inventory_weather_region_v2_festival_demand.csv") -> List["WeatherFestivalDemandRecord"]:
        """Load the weather-and-festival enriched demand dataset."""
        from agents.inventory_monitoring.models.inventory_models import WeatherFestivalDemandRecord

        file_path = self._resolve_data_file(file_name)
        rows = self._read_rows(file_path)

        records: List[WeatherFestivalDemandRecord] = []
        for row in rows:
            try:
                record = WeatherFestivalDemandRecord(
                    date=row.get("date", "").strip(),
                    sku_id=parse_int(row.get("product_id") or row.get("sku_id")),
                    location_id=parse_int(row.get("location_id")),
                    category_id=parse_optional_int(row.get("category_id")),
                    velocity_class_id=parse_optional_int(row.get("velocity_class_id")),
                    on_hand_qty=parse_optional_float(row.get("on_hand_qty")),
                    allocated_qty=parse_optional_float(row.get("allocated_qty")),
                    safety_stock_qty=parse_optional_float(row.get("safety_stock_qty")),
                    reorder_point_qty=parse_optional_float(row.get("reorder_point_qty")),
                    daily_demand=parse_optional_float(row.get("daily_demand")),
                    demand_std_dev=parse_optional_float(row.get("demand_std_dev")),
                    lead_time_days=parse_optional_float(row.get("lead_time_days")),
                    supplier_id=parse_optional_int(row.get("supplier_id")),
                    avg_retail_price=parse_optional_float(row.get("avg_retail_price")),
                    holding_cost_per_unit_day=parse_optional_float(row.get("holding_cost_per_unit_day")),
                    handling_cost_per_unit=parse_optional_float(row.get("handling_cost_per_unit")),
                    order_fulfillment_rate=parse_optional_float(row.get("order_fulfillment_rate")),
                    total_orders_last_month=parse_optional_float(row.get("total_orders_last_month")),
                    turnover_ratio=parse_optional_float(row.get("turnover_ratio")),
                    annual_units_max=parse_optional_float(row.get("annual_units_max")),
                    season_multiplier=parse_optional_float(row.get("season_multiplier")),
                    is_promotional=parse_bool(row.get("is_promotional")),
                    month=parse_optional_int(row.get("month")),
                    quarter=parse_optional_int(row.get("quarter")),
                    day_of_year=parse_optional_int(row.get("day_of_year")),
                    month_sin=parse_optional_float(row.get("month_sin")),
                    month_cos=parse_optional_float(row.get("month_cos")),
                    is_promotional_int=parse_optional_int(row.get("is_promotional_int")),
                    stock_gap=parse_optional_float(row.get("stock_gap")),
                    available_stock=parse_optional_float(row.get("available_stock")),
                    safety_ratio=parse_optional_float(row.get("safety_ratio")),
                    velocity_score=parse_optional_float(row.get("velocity_score")),
                    country=row.get("country", "").strip() or None,
                    country_code=row.get("country_code", "").strip() or None,
                    state_province=row.get("state_province", "").strip() or None,
                    city=row.get("city", "").strip() or None,
                    climate_zone=row.get("climate_zone", "").strip() or None,
                    population_index=parse_optional_float(row.get("population_index")),
                    income_index=parse_optional_float(row.get("income_index")),
                    urbanization_score=parse_optional_float(row.get("urbanization_score")),
                    regional_demand_index=parse_optional_float(row.get("regional_demand_index")),
                    consumer_spending_index=parse_optional_float(row.get("consumer_spending_index")),
                    weather_sensitivity_score=parse_optional_float(row.get("weather_sensitivity_score")),
                    logistics_complexity_score=parse_optional_float(row.get("logistics_complexity_score")),
                    distance_to_dc_km=parse_optional_float(row.get("distance_to_dc_km")),
                    regional_supply_risk_score=parse_optional_float(row.get("regional_supply_risk_score")),
                    market_maturity_index=parse_optional_float(row.get("market_maturity_index")),
                    temperature_c=parse_optional_float(row.get("temperature_c")),
                    feels_like_c=parse_optional_float(row.get("feels_like_c")),
                    humidity_pct=parse_optional_float(row.get("humidity_pct")),
                    rainfall_mm=parse_optional_float(row.get("rainfall_mm")),
                    snowfall_cm=parse_optional_float(row.get("snowfall_cm")),
                    wind_speed_kmh=parse_optional_float(row.get("wind_speed_kmh")),
                    uv_index=parse_optional_float(row.get("uv_index")),
                    cloud_cover_pct=parse_optional_float(row.get("cloud_cover_pct")),
                    pressure_hpa=parse_optional_float(row.get("pressure_hpa")),
                    visibility_km=parse_optional_float(row.get("visibility_km")),
                    heatwave_flag=parse_bool(row.get("heatwave_flag")),
                    coldwave_flag=parse_bool(row.get("coldwave_flag")),
                    monsoon_flag=parse_bool(row.get("monsoon_flag")),
                    heavy_rain_flag=parse_bool(row.get("heavy_rain_flag")),
                    snowfall_flag=parse_bool(row.get("snowfall_flag")),
                    extreme_weather_flag=parse_bool(row.get("extreme_weather_flag")),
                    temperature_deviation=parse_optional_float(row.get("temperature_deviation")),
                    rainfall_deviation=parse_optional_float(row.get("rainfall_deviation")),
                    weather_severity_index=parse_optional_float(row.get("weather_severity_index")),
                    weather_demand_multiplier=parse_optional_float(row.get("weather_demand_multiplier")),
                    weather_supply_risk_score=parse_optional_float(row.get("weather_supply_risk_score")),
                    climate_anomaly_score=parse_optional_float(row.get("climate_anomaly_score")),
                    weather_confidence_score=parse_optional_float(row.get("weather_confidence_score")),
                    weather_adjusted_demand=parse_optional_float(row.get("weather_adjusted_demand")),
                    regional_adjusted_demand=parse_optional_float(row.get("regional_adjusted_demand")),
                    weather_adjusted_safety_stock=parse_optional_float(row.get("weather_adjusted_safety_stock")),
                    weather_adjusted_reorder_point=parse_optional_float(row.get("weather_adjusted_reorder_point")),
                    demand_volatility_score=parse_optional_float(row.get("demand_volatility_score")),
                    supply_disruption_risk=parse_optional_float(row.get("supply_disruption_risk")),
                    stockout_weather_risk=parse_optional_float(row.get("stockout_weather_risk")),
                    inventory_weather_pressure=parse_optional_float(row.get("inventory_weather_pressure")),
                    regional_inventory_risk=parse_optional_float(row.get("regional_inventory_risk")),
                    day_of_week=parse_optional_int(row.get("day_of_week")),
                    week_of_year=parse_optional_int(row.get("week_of_year")),
                    season=row.get("season", "").strip() or None,
                    forecast_demand_next_7_days=parse_optional_float(row.get("forecast_demand_next_7_days")),
                    forecast_demand_next_14_days=parse_optional_float(row.get("forecast_demand_next_14_days")),
                    forecast_demand_next_30_days=parse_optional_float(row.get("forecast_demand_next_30_days")),
                    is_festival_day=parse_bool(row.get("is_festival_day")),
                    days_to_next_festival=parse_optional_float(row.get("days_to_next_festival")),
                    days_since_last_festival=parse_optional_float(row.get("days_since_last_festival")),
                    festival_proximity_score=parse_optional_float(row.get("festival_proximity_score")),
                    is_shopping_season=parse_bool(row.get("is_shopping_season")),
                    daily_demand_pre_festival_adjustment=parse_optional_float(row.get("daily_demand_pre_festival_adjustment")),
                )
                records.append(record)
            except Exception as e:
                logger.error(f"Error parsing weather/festival row: {e}")
                continue
        return records

    def _resolve_data_file(self, file_name: str | Path) -> Path:
        """Resolve a data file from the loader root or the workspace root."""
        candidate = Path(file_name)
        if candidate.is_absolute() and candidate.exists():
            return candidate

        local_path = self.root_dir / candidate
        if local_path.exists():
            return local_path

        workspace_root = self.root_dir.parent
        if workspace_root.exists():
            workspace_candidate = workspace_root / candidate
            if workspace_candidate.exists():
                return workspace_candidate

        return local_path

    def load_in_transit_inventory(self) -> List[Dict[str, int]]:
        """Load in-transit inventory from CSV."""
        rows = self._read_rows(self.root_dir / "db3_csv_export" / "in_transit_inventory.csv")
        in_transit = []
        for row in rows:
            try:
                item = {
                    "sku_id": parse_int(row.get("sku_id") or row.get("product_id")),
                    "location_id": parse_int(row.get("destination_location_id")),
                    "quantity_in_transit": parse_int(row.get("quantity_in_transit")),
                }
                in_transit.append(item)
            except Exception as e:
                logger.error(f"Error parsing in-transit inventory row: {e}")
                continue
        return in_transit

    def load_inventory_events(self) -> List[Dict]:
        """Load inventory events from CSV."""
        rows = self._read_rows(self.root_dir / "db5_csv_export" / "inventory_events.csv")
        events = []
        for row in rows:
            try:
                event = {
                    "event_id": parse_int(row.get("event_id")),
                    "event_type": row.get("event_type", "").strip(),
                    "sku_id": parse_int(row.get("sku_id")),
                    "location_id": parse_int(row.get("location_id")),
                    "quantity_change": parse_int(row.get("quantity_change")),
                    "event_timestamp": row.get("event_timestamp", "").strip(),
                    "reference_id": row.get("reference_id", "").strip(),
                    "source_location_id": parse_optional_int(row.get("source_location_id")),
                    "destination_location_id": parse_optional_int(row.get("destination_location_id")),
                    "event_reason": row.get("event_reason", "").strip(),
                    "created_by": row.get("created_by", "").strip(),
                }
                events.append(event)
            except Exception as e:
                logger.error(f"Error parsing inventory event row: {e}")
                continue
        return events

    # ============================================================================
    # DB1: Store & Warehouse Network (Locations)
    # ============================================================================

    def load_locations(self) -> List[Dict]:
        """Load master locations table (stores + distribution centers)."""
        rows = self._read_rows(self.root_dir / "db1_csv_export" / "locations.csv")
        locations = []
        for row in rows:
            try:
                location = {
                    "location_id": parse_int(row.get("location_id")),
                    "location_name": row.get("location_name", "").strip(),
                    "location_type": row.get("location_type", "").strip(),
                    "state_id": parse_int(row.get("state_id")),
                    "active_flag": row.get("active_flag", "").strip().lower() == "true",
                }
                locations.append(location)
            except Exception as e:
                logger.error(f"Error parsing location row: {e}")
                continue
        return locations

    def load_stores(self) -> List[Dict]:
        """Load retail stores data."""
        rows = self._read_rows(self.root_dir / "db1_csv_export" / "stores.csv")
        stores = []
        for row in rows:
            try:
                store = {
                    "store_id": parse_int(row.get("store_id")),
                    "store_code": row.get("store_code", "").strip(),
                    "store_name": row.get("store_name", "").strip(),
                    "city": row.get("city", "").strip(),
                    "state_id": parse_int(row.get("state_id")),
                    "format_id": parse_int(row.get("format_id")),
                    "dc_id": parse_int(row.get("dc_id")),
                    "opening_date": row.get("opening_date", "").strip(),
                    "active_flag": row.get("active_flag", "").strip().lower() == "true",
                }
                stores.append(store)
            except Exception as e:
                logger.error(f"Error parsing store row: {e}")
                continue
        return stores

    def load_distribution_centers(self) -> List[Dict]:
        """Load distribution centers data."""
        rows = self._read_rows(self.root_dir / "db1_csv_export" / "distribution_centers.csv")
        dcs = []
        for row in rows:
            try:
                dc = {
                    "dc_id": parse_int(row.get("dc_id")),
                    "dc_name": row.get("dc_name", "").strip(),
                    "region": row.get("region", "").strip(),
                    "city": row.get("city", "").strip(),
                    "state_id": parse_int(row.get("state_id")),
                }
                dcs.append(dc)
            except Exception as e:
                logger.error(f"Error parsing distribution center row: {e}")
                continue
        return dcs

    def load_states(self) -> List[Dict]:
        """Load states reference data."""
        rows = self._read_rows(self.root_dir / "db1_csv_export" / "states.csv")
        states = []
        for row in rows:
            try:
                state = {
                    "state_id": parse_int(row.get("state_id")),
                    "state_name": row.get("state_name", "").strip(),
                    "state_code": row.get("state_code", "").strip(),
                }
                states.append(state)
            except Exception as e:
                logger.error(f"Error parsing state row: {e}")
                continue
        return states

    def load_store_formats(self) -> List[Dict]:
        """Load store formats reference data."""
        rows = self._read_rows(self.root_dir / "db1_csv_export" / "store_formats.csv")
        formats = []
        for row in rows:
            try:
                fmt = {
                    "format_id": parse_int(row.get("format_id")),
                    "format_name": row.get("format_name", "").strip(),
                    "square_feet": parse_int(row.get("square_feet")),
                }
                formats.append(fmt)
            except Exception as e:
                logger.error(f"Error parsing store format row: {e}")
                continue
        return formats

    # ============================================================================
    # DB2: Product Master Data
    # ============================================================================

    def load_products(self) -> List[Dict]:
        """Load product master data (5,000 SKUs)."""
        rows = self._read_rows(self.root_dir / "db2_csv_export" / "products.csv")
        products = []
        for row in rows:
            try:
                product = {
                    "sku_id": parse_int(row.get("sku_id") or row.get("product_id")),
                    "product_name": row.get("product_name", "").strip(),
                    "category_id": parse_int(row.get("category_id")),
                    "velocity_class": row.get("velocity_class", "").strip(),
                    "unit_cost": float(row.get("unit_cost", 0) or 0),
                    "unit_price": float(row.get("unit_price", 0) or 0),
                }
                products.append(product)
            except Exception as e:
                logger.error(f"Error parsing product row: {e}")
                continue
        return products

    def load_product_categories(self) -> List[Dict]:
        """Load product categories."""
        rows = self._read_rows(self.root_dir / "db2_csv_export" / "product_categories.csv")
        categories = []
        for row in rows:
            try:
                category = {
                    "category_id": parse_int(row.get("category_id")),
                    "category_name": row.get("category_name", "").strip(),
                    "category_description": row.get("category_description", "").strip(),
                }
                categories.append(category)
            except Exception as e:
                logger.error(f"Error parsing product category row: {e}")
                continue
        return categories

    def load_seasonal_patterns(self) -> List[Dict]:
        """Load seasonal demand patterns for demand forecasting."""
        rows = self._read_rows(self.root_dir / "db2_csv_export" / "seasonal_patterns.csv")
        patterns = []
        for row in rows:
            try:
                pattern = {
                    "sku_id": parse_int(row.get("sku_id")),
                    "month": parse_int(row.get("month")),
                    "seasonal_factor": float(row.get("seasonal_factor", 1.0) or 1.0),
                    "avg_monthly_demand": parse_int(row.get("avg_monthly_demand")),
                }
                patterns.append(pattern)
            except Exception as e:
                logger.error(f"Error parsing seasonal pattern row: {e}")
                continue
        return patterns

    def load_velocity_classes(self) -> List[Dict]:
        """Load velocity classifications for SKUs."""
        rows = self._read_rows(self.root_dir / "db2_csv_export" / "velocity_classes.csv")
        classes = []
        for row in rows:
            try:
                vc = {
                    "velocity_class": row.get("velocity_class", "").strip(),
                    "description": row.get("description", "").strip(),
                    "min_annual_turns": parse_int(row.get("min_annual_turns")),
                    "max_annual_turns": parse_int(row.get("max_annual_turns")),
                }
                classes.append(vc)
            except Exception as e:
                logger.error(f"Error parsing velocity class row: {e}")
                continue
        return classes

    # ============================================================================
    # DB4: Supplier & Procurement Data
    # ============================================================================

    def load_suppliers(self) -> List[Dict]:
        """Load supplier master data (35 suppliers)."""
        rows = self._read_rows(self.root_dir / "db4_csv_export" / "suppliers.csv")
        suppliers = []
        for row in rows:
            try:
                supplier = {
                    "supplier_id": parse_int(row.get("supplier_id")),
                    "supplier_name": row.get("supplier_name", "").strip(),
                    "primary_contact": row.get("primary_contact", "").strip(),
                    "lead_time_days": parse_int(row.get("lead_time_days")),
                    "minimum_order_qty": parse_int(row.get("minimum_order_qty")),
                    "payment_terms_id": parse_int(row.get("payment_terms_id")),
                }
                suppliers.append(supplier)
            except Exception as e:
                logger.error(f"Error parsing supplier row: {e}")
                continue
        return suppliers

    def load_supplier_performance_metrics(self) -> List[Dict]:
        """Load supplier performance and reliability data."""
        rows = self._read_rows(self.root_dir / "db4_csv_export" / "supplier_performance_metrics.csv")
        metrics = []
        for row in rows:
            try:
                metric = {
                    "supplier_id": parse_int(row.get("supplier_id")),
                    "on_time_delivery_rate": float(row.get("on_time_delivery_rate", 0) or 0),
                    "quality_score": float(row.get("quality_score", 0) or 0),
                    "response_time_hours": parse_int(row.get("response_time_hours")),
                    "defect_rate": float(row.get("defect_rate", 0) or 0),
                }
                metrics.append(metric)
            except Exception as e:
                logger.error(f"Error parsing supplier performance metric row: {e}")
                continue
        return metrics

    def load_supplier_pricing_tiers(self) -> List[Dict]:
        """Load supplier pricing tiers for different purchase volumes."""
        rows = self._read_rows(self.root_dir / "db4_csv_export" / "supplier_pricing_tiers.csv")
        tiers = []
        for row in rows:
            try:
                tier = {
                    "pricing_tier_id": parse_int(row.get("pricing_tier_id") or row.get("tier_id")),
                    "supplier_id": parse_int(row.get("supplier_id")),
                    "category_id": parse_int(row.get("category_id")),
                    "min_qty": parse_int(row.get("min_qty") or row.get("min_quantity")),
                    "max_qty": parse_int(row.get("max_qty") or row.get("max_quantity")),
                    "discount_percent": float(row.get("discount_percent", 0) or 0),
                }
                tiers.append(tier)
            except Exception as e:
                logger.error(f"Error parsing supplier pricing tier row: {e}")
                continue
        return tiers

    def load_supplier_category_mapping(self) -> List[Dict]:
        """Load supplier category mapping and baseline cost data."""
        rows = self._read_rows(self.root_dir / "db4_csv_export" / "supplier_category_mapping.csv")
        mappings = []
        for row in rows:
            try:
                mapping = {
                    "mapping_id": parse_int(row.get("mapping_id")),
                    "supplier_id": parse_int(row.get("supplier_id")),
                    "category_id": parse_int(row.get("category_id")),
                    "lead_time_days": parse_int(row.get("lead_time_days")),
                    "moq_units": parse_int(row.get("moq_units")),
                    "unit_cost": float(row.get("unit_cost", 0) or 0),
                }
                mappings.append(mapping)
            except Exception as e:
                logger.error(f"Error parsing supplier category mapping row: {e}")
                continue
        return mappings

    def load_supplier_risk_profile(self) -> List[Dict]:
        """Load supplier risk profiles for supplier evaluation."""
        rows = self._read_rows(self.root_dir / "db4_csv_export" / "supplier_risk_profile.csv")
        profiles = []
        for row in rows:
            try:
                profile = {
                    "supplier_id": parse_int(row.get("supplier_id")),
                    "financial_stability_score": float(row.get("financial_stability_score", 0) or 0),
                    "geographic_risk": row.get("geographic_risk", "").strip(),
                    "regulatory_compliance_status": row.get("regulatory_compliance_status", "").strip(),
                    "bankruptcy_risk_level": row.get("bankruptcy_risk_level", "").strip(),
                }
                profiles.append(profile)
            except Exception as e:
                logger.error(f"Error parsing supplier risk profile row: {e}")
                continue
        return profiles

    # ============================================================================
    # DB6: Weather, Festival & Regional Demand Context
    # ============================================================================

    def load_demand_context_fact(self) -> List[Dict]:
        """Load the demand context fact table from db6 (weather + festival signals).

        This table is the synthetic schema-equivalent of
        synthetic_inventory_weather_region_v2_festival_demand.csv.  When the
        real LFS file is available it supersedes this table (see
        load_weather_festival_dataset).  This loader exists so the full
        pipeline and tests can run in offline/dev mode without the 469 MB
        LFS asset.
        """
        rows = self._read_rows(
            self.root_dir / "db6_csv_export" / "demand_context_fact.csv"
        )
        records = []
        for row in rows:
            try:
                record = {
                    "date": row.get("date", "").strip(),
                    "product_id": parse_int(row.get("product_id") or row.get("sku_id")),
                    "location_id": parse_int(row.get("location_id")),
                    "temperature_c": parse_optional_float(row.get("temperature_c")),
                    "feels_like_c": parse_optional_float(row.get("feels_like_c")),
                    "humidity_pct": parse_optional_float(row.get("humidity_pct")),
                    "rainfall_mm": parse_optional_float(row.get("rainfall_mm")),
                    "snowfall_cm": parse_optional_float(row.get("snowfall_cm")),
                    "wind_speed_kmh": parse_optional_float(row.get("wind_speed_kmh")),
                    "uv_index": parse_optional_float(row.get("uv_index")),
                    "cloud_cover_pct": parse_optional_float(row.get("cloud_cover_pct")),
                    "pressure_hpa": parse_optional_float(row.get("pressure_hpa")),
                    "visibility_km": parse_optional_float(row.get("visibility_km")),
                    "heatwave_flag": parse_bool(row.get("heatwave_flag")),
                    "coldwave_flag": parse_bool(row.get("coldwave_flag")),
                    "monsoon_flag": parse_bool(row.get("monsoon_flag")),
                    "heavy_rain_flag": parse_bool(row.get("heavy_rain_flag")),
                    "snowfall_flag": parse_bool(row.get("snowfall_flag")),
                    "extreme_weather_flag": parse_bool(row.get("extreme_weather_flag")),
                    "temperature_deviation": parse_optional_float(row.get("temperature_deviation")),
                    "rainfall_deviation": parse_optional_float(row.get("rainfall_deviation")),
                    "weather_severity_index": parse_optional_float(row.get("weather_severity_index")),
                    "weather_demand_multiplier": parse_optional_float(row.get("weather_demand_multiplier")),
                    "weather_supply_risk_score": parse_optional_float(row.get("weather_supply_risk_score")),
                    "climate_anomaly_score": parse_optional_float(row.get("climate_anomaly_score")),
                    "weather_confidence_score": parse_optional_float(row.get("weather_confidence_score")),
                    "weather_adjusted_demand": parse_optional_float(row.get("weather_adjusted_demand")),
                    "regional_adjusted_demand": parse_optional_float(row.get("regional_adjusted_demand")),
                    "weather_adjusted_safety_stock": parse_optional_float(row.get("weather_adjusted_safety_stock")),
                    "weather_adjusted_reorder_point": parse_optional_float(row.get("weather_adjusted_reorder_point")),
                    "demand_volatility_score": parse_optional_float(row.get("demand_volatility_score")),
                    "supply_disruption_risk": parse_optional_float(row.get("supply_disruption_risk")),
                    "stockout_weather_risk": parse_optional_float(row.get("stockout_weather_risk")),
                    "inventory_weather_pressure": parse_optional_float(row.get("inventory_weather_pressure")),
                    "regional_inventory_risk": parse_optional_float(row.get("regional_inventory_risk")),
                    "is_festival_day": parse_bool(row.get("is_festival_day")),
                    "days_to_next_festival": parse_optional_float(row.get("days_to_next_festival")),
                    "days_since_last_festival": parse_optional_float(row.get("days_since_last_festival")),
                    "festival_proximity_score": parse_optional_float(row.get("festival_proximity_score")),
                    "is_shopping_season": parse_bool(row.get("is_shopping_season")),
                    "daily_demand_pre_festival_adjustment": parse_optional_float(
                        row.get("daily_demand_pre_festival_adjustment")
                    ),
                    "season": row.get("season", "").strip() or None,
                    "regional_demand_index": parse_optional_float(row.get("regional_demand_index")),
                    "day_of_week": parse_optional_int(row.get("day_of_week")),
                    "week_of_year": parse_optional_int(row.get("week_of_year")),
                    "forecast_demand_next_7_days": parse_optional_float(row.get("forecast_demand_next_7_days")),
                    "forecast_demand_next_14_days": parse_optional_float(row.get("forecast_demand_next_14_days")),
                    "forecast_demand_next_30_days": parse_optional_float(row.get("forecast_demand_next_30_days")),
                }
                records.append(record)
            except Exception as e:
                logger.error(f"Error parsing demand context fact row: {e}")
                continue
        return records

    def load_festival_calendar(self) -> List[Dict]:
        """Load the festival calendar reference table from db6."""
        rows = self._read_rows(
            self.root_dir / "db6_csv_export" / "festival_calendar.csv"
        )
        festivals = []
        for row in rows:
            try:
                festival = {
                    "festival_id": parse_int(row.get("festival_id")),
                    "festival_name": row.get("festival_name", "").strip(),
                    "location_id": parse_int(row.get("location_id")),
                    "start_date": row.get("start_date", "").strip(),
                    "end_date": row.get("end_date", "").strip(),
                    "demand_lift_pct": parse_optional_float(row.get("demand_lift_pct")),
                    "supply_risk_score": parse_optional_float(row.get("supply_risk_score")),
                    "festival_type": row.get("festival_type", "").strip(),
                }
                festivals.append(festival)
            except Exception as e:
                logger.error(f"Error parsing festival calendar row: {e}")
                continue
        return festivals

    def load_location_climate_profile(self) -> List[Dict]:
        """Load the location climate profile reference table from db6."""
        rows = self._read_rows(
            self.root_dir / "db6_csv_export" / "location_climate_profile.csv"
        )
        profiles = []
        for row in rows:
            try:
                profile = {
                    "location_id": parse_int(row.get("location_id")),
                    "climate_zone": row.get("climate_zone", "").strip() or None,
                    "avg_temp_c": parse_optional_float(row.get("avg_temp_c")),
                    "avg_rainfall_mm_annual": parse_optional_float(row.get("avg_rainfall_mm_annual")),
                    "weather_sensitivity_score": parse_optional_float(row.get("weather_sensitivity_score")),
                    "logistics_complexity_score": parse_optional_float(row.get("logistics_complexity_score")),
                    "regional_demand_index": parse_optional_float(row.get("regional_demand_index")),
                    "population_index": parse_optional_float(row.get("population_index")),
                    "income_index": parse_optional_float(row.get("income_index")),
                    "urbanization_score": parse_optional_float(row.get("urbanization_score")),
                    "consumer_spending_index": parse_optional_float(row.get("consumer_spending_index")),
                    "distance_to_dc_km": parse_optional_float(row.get("distance_to_dc_km")),
                    "regional_supply_risk_score": parse_optional_float(row.get("regional_supply_risk_score")),
                    "market_maturity_index": parse_optional_float(row.get("market_maturity_index")),
                }
                profiles.append(profile)
            except Exception as e:
                logger.error(f"Error parsing location climate profile row: {e}")
                continue
        return profiles

    def build_weather_context_map(
        self,
        source: str = "auto",
    ) -> "dict[tuple[int, int], WeatherFestivalContext]":
        """Build a (sku_id, location_id) → WeatherFestivalContext lookup dict.

        This is the primary pipeline integration point for weather/festival
        signals.  It is called once at agent startup and the resulting dict
        is passed into InventoryRiskMonitoringService and the orchestrator
        payload builder for O(1) per-row enrichment.

        Source selection strategy
        -------------------------
        ``source='auto'`` (default):
            1. Try to load the full LFS dataset
               (synthetic_inventory_weather_region_v2_festival_demand.csv) from
               the workspace root.  This file is 469 MB and gives the richest
               signal when available.
            2. Fall back to db6_csv_export/demand_context_fact.csv (synthetic
               samples) so offline dev / CI always works without the LFS asset.
        ``source='lfs'``  — force the LFS file; raise if absent.
        ``source='db6'``  — force the synthetic db6 samples.

        When multiple rows exist for the same (sku_id, location_id) the most
        recent date row is kept (mimics a "latest available context" query).

        Returns
        -------
        dict mapping (sku_id, location_id) → WeatherFestivalContext.
        Returns an empty dict (not an error) if no data source is readable,
        so the rest of the pipeline degrades gracefully.
        """
        from agents.inventory_monitoring.models.inventory_models import WeatherFestivalContext

        records: list = []

        if source in ("auto", "lfs"):
            try:
                lfs_records = self.load_weather_festival_dataset()
                if lfs_records:
                    logger.info(
                        f"build_weather_context_map: loaded {len(lfs_records)} rows "
                        "from LFS weather/festival dataset"
                    )
                    # Convert WeatherFestivalDemandRecord objects to context dicts
                    context_map: dict[tuple[int, int], WeatherFestivalContext] = {}
                    for rec in lfs_records:
                        key = (rec.sku_id, rec.location_id)
                        existing = context_map.get(key)
                        if existing is None or (rec.date and rec.date > getattr(existing, "_date", "")):
                            ctx = rec.to_weather_festival_context()
                            # Stash date for recency comparison (not part of the public API)
                            ctx._date = rec.date  # type: ignore[attr-defined]
                            context_map[key] = ctx
                    logger.info(
                        f"build_weather_context_map: built context for "
                        f"{len(context_map)} (sku_id, location_id) pairs from LFS file"
                    )
                    return context_map
            except Exception as e:
                if source == "lfs":
                    raise
                logger.info(
                    f"build_weather_context_map: LFS dataset not available ({e}), "
                    "falling back to db6 samples"
                )

        # Fall back to (or explicitly use) the db6 synthetic samples
        try:
            records = self.load_demand_context_fact()
        except Exception as e:
            logger.warning(f"build_weather_context_map: could not load db6 samples: {e}")
            return {}

        if not records:
            logger.warning(
                "build_weather_context_map: no demand context records found; "
                "weather/festival enrichment will be skipped for this run"
            )
            return {}

        # Build map from db6 dict records — keep most recent row per key
        date_by_key: dict[tuple[int, int], str] = {}
        context_map_db6: dict[tuple[int, int], WeatherFestivalContext] = {}

        for row in records:
            sku_id = row.get("product_id")
            location_id = row.get("location_id")
            if sku_id is None or location_id is None:
                continue
            key = (sku_id, location_id)
            row_date = row.get("date", "")
            if key in date_by_key and row_date <= date_by_key[key]:
                continue
            date_by_key[key] = row_date
            context_map_db6[key] = WeatherFestivalContext(
                weather_demand_multiplier=row.get("weather_demand_multiplier") or 1.0,
                weather_severity_index=row.get("weather_severity_index") or 0.0,
                weather_supply_risk_score=row.get("weather_supply_risk_score") or 0.0,
                climate_anomaly_score=row.get("climate_anomaly_score") or 0.0,
                weather_confidence_score=row.get("weather_confidence_score") or 1.0,
                supply_disruption_risk=row.get("supply_disruption_risk") or 0.0,
                stockout_weather_risk=row.get("stockout_weather_risk") or 0.0,
                inventory_weather_pressure=row.get("inventory_weather_pressure") or 0.0,
                regional_inventory_risk=row.get("regional_inventory_risk") or 0.0,
                heatwave_flag=bool(row.get("heatwave_flag")),
                coldwave_flag=bool(row.get("coldwave_flag")),
                monsoon_flag=bool(row.get("monsoon_flag")),
                heavy_rain_flag=bool(row.get("heavy_rain_flag")),
                snowfall_flag=bool(row.get("snowfall_flag")),
                extreme_weather_flag=bool(row.get("extreme_weather_flag")),
                temperature_c=row.get("temperature_c"),
                humidity_pct=row.get("humidity_pct"),
                rainfall_mm=row.get("rainfall_mm"),
                snowfall_cm=row.get("snowfall_cm"),
                weather_adjusted_demand=row.get("weather_adjusted_demand"),
                weather_adjusted_safety_stock=row.get("weather_adjusted_safety_stock"),
                weather_adjusted_reorder_point=row.get("weather_adjusted_reorder_point"),
                is_festival_day=bool(row.get("is_festival_day")),
                days_to_next_festival=row.get("days_to_next_festival"),
                festival_proximity_score=row.get("festival_proximity_score") or 0.0,
                is_shopping_season=bool(row.get("is_shopping_season")),
                daily_demand_pre_festival_adjustment=row.get("daily_demand_pre_festival_adjustment"),
                regional_demand_index=row.get("regional_demand_index") or 1.0,
                regional_adjusted_demand=row.get("regional_adjusted_demand"),
                season=row.get("season"),
            )

        logger.info(
            f"build_weather_context_map: built context for "
            f"{len(context_map_db6)} (sku_id, location_id) pairs from db6 samples"
        )
        return context_map_db6
