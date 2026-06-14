from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .models import InventoryEvent, InventoryPosition, InventorySnapshot


def _parse_int(value: Optional[str], default: int = 0) -> int:
    if value is None:
        return default
    value = value.strip().replace("\ufeff", "")
    if value == "" or value.upper() in {"NULL", "NONE"}:
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip().replace("\ufeff", "")
    if value == "" or value.upper() in {"NULL", "NONE"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


class CsvInventoryDataLoader:
    """Loads inventory agent data from the csv_exports folder."""

    def __init__(self, root_dir: str | Path = "csv_exports") -> None:
        self.root_dir = Path(root_dir)

    def _read_rows(self, file_path: Path) -> List[Dict[str, str]]:
        if not file_path.exists():
            return []

        with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            rows: List[Dict[str, str]] = []
            for row in reader:
                normalized = {key.strip().lstrip("\ufeff"): (value or "") for key, value in row.items()}
                rows.append(normalized)
            return rows

    def load_inventory_events(self) -> List[InventoryEvent]:
        rows = self._read_rows(self.root_dir / "db5_csv_export" / "inventory_events.csv")
        return [
            InventoryEvent(
                event_id=_parse_int(row.get("event_id")),
                event_type=row.get("event_type", "").strip(),
                sku_id=_parse_int(row.get("sku_id")),
                location_id=_parse_int(row.get("location_id")),
                quantity_change=_parse_int(row.get("quantity_change")),
                event_timestamp=row.get("event_timestamp", "").strip(),
                reference_id=row.get("reference_id", "").strip(),
                source_location_id=_parse_optional_int(row.get("source_location_id")),
                destination_location_id=_parse_optional_int(row.get("destination_location_id")),
                event_reason=row.get("event_reason", "").strip(),
                created_by=row.get("created_by", "").strip(),
            )
            for row in rows
        ]

    def load_inventory_positions(self) -> List[InventoryPosition]:
        rows = self._read_rows(self.root_dir / "db3_csv_export" / "inventory_positions.csv")
        return [
            InventoryPosition(
                position_id=_parse_int(row.get("position_id")),
                sku_id=_parse_int(row.get("product_id") or row.get("product_id", "")),
                location_id=_parse_int(row.get("location_id")),
                on_hand_qty=_parse_int(row.get("on_hand_qty")),
                safety_stock_qty=_parse_int(row.get("safety_stock_qty")),
                reorder_point_qty=_parse_int(row.get("reorder_point_qty")),
                allocated_qty=_parse_int(row.get("allocated_qty")),
                last_counted_date=row.get("last_counted_date", "").strip() or None,
            )
            for row in rows
        ]

    def load_inventory_daily_snapshots(self) -> List[InventorySnapshot]:
        rows = self._read_rows(self.root_dir / "db5_csv_export" / "inventory_daily_snapshots.csv")
        return [
            InventorySnapshot(
                snapshot_id=_parse_int(row.get("snapshot_id")),
                snapshot_date=row.get("snapshot_date", "").strip(),
                sku_id=_parse_int(row.get("sku_id")),
                location_id=_parse_int(row.get("location_id")),
                opening_stock=_parse_int(row.get("opening_stock")),
                receipts=_parse_int(row.get("receipts")),
                sales=_parse_int(row.get("sales")),
                transfers_in=_parse_int(row.get("transfers_in")),
                transfers_out=_parse_int(row.get("transfers_out")),
                adjustments=_parse_int(row.get("adjustments")),
                closing_stock=_parse_int(row.get("closing_stock")),
            )
            for row in rows
        ]

    def load_in_transit_inventory(self) -> List[Dict[str, int]]:
        rows = self._read_rows(self.root_dir / "db3_csv_export" / "in_transit_inventory.csv")
        return [
            {
                "sku_id": _parse_int(row.get("product_id")),
                "location_id": _parse_int(row.get("destination_location_id")),
                "quantity_in_transit": _parse_int(row.get("quantity_in_transit")),
            }
            for row in rows
        ]
