from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .parsing import parse_int, parse_optional_int

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

    def load_inventory_positions(self) -> List[InventoryPosition]:
        """Load inventory positions from CSV."""
        rows = self._read_rows(self.root_dir / "db3_csv_export" / "inventory_positions.csv")
        # Local import to avoid circular import at module import time
        from agents.inventory_monitoring.models.inventory_models import InventoryPosition

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
                    "pricing_tier_id": parse_int(row.get("pricing_tier_id")),
                    "supplier_id": parse_int(row.get("supplier_id")),
                    "sku_id": parse_int(row.get("sku_id") or row.get("product_id")),
                    "min_qty": parse_int(row.get("min_qty")),
                    "max_qty": parse_int(row.get("max_qty")),
                    "unit_price": float(row.get("unit_price", 0) or 0),
                }
                tiers.append(tier)
            except Exception as e:
                logger.error(f"Error parsing supplier pricing tier row: {e}")
                continue
        return tiers

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
