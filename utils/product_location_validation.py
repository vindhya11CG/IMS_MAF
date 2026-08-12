from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple


def _parse_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text or text.lower() in {"", "null", "none"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"", "null", "none"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _read_id_set(path: Path, column_name: str) -> Set[int]:
    if not path.exists():
        return set()

    values: Set[int] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            parsed = _parse_int(row.get(column_name))
            if parsed is not None:
                values.add(parsed)
    return values


def _read_pair_set(path: Path) -> Set[Tuple[int, int]]:
    if not path.exists():
        return set()

    pairs: Set[Tuple[int, int]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            product_id = _parse_int(row.get("product_id") or row.get("sku_id"))
            location_id = _parse_int(row.get("location_id"))
            if product_id is not None and location_id is not None:
                pairs.add((product_id, location_id))
    return pairs


def _read_pair_value_map(path: Path, field_names: List[str]) -> Dict[Tuple[int, int], Dict[str, float | None]]:
    if not path.exists():
        return {}

    values: Dict[Tuple[int, int], Dict[str, float | None]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            product_id = _parse_int(row.get("product_id") or row.get("sku_id"))
            location_id = _parse_int(row.get("location_id"))
            if product_id is None or location_id is None:
                continue
            key = (product_id, location_id)
            values[key] = {
                field: _parse_float(row.get(field)) for field in field_names
            }
    return values


def generate_product_location_consistency_report(root_dir: str | Path = "data/csv_exports") -> Dict[str, object]:
    """Build a report for product/location coverage and value consistency across inventory and demand data."""
    root = Path(root_dir)
    if not (root / "db3_csv_export").exists():
        candidate = root / "data" / "csv_exports"
        if candidate.exists():
            root = candidate

    inventory_path = root / "db3_csv_export" / "inventory_positions.csv"
    products_path = root / "db2_csv_export" / "products.csv"
    locations_path = root / "db1_csv_export" / "locations.csv"
    demand_context_path = root / "db6_csv_export" / "demand_context_fact.csv"
    synthetic_path = root.parent / "synthetic_inventory_weather_region_v2_festival_demand.csv"

    inventory_pairs = _read_pair_set(inventory_path)
    context_pairs = _read_pair_set(demand_context_path)
    inventory_values = _read_pair_value_map(
        inventory_path,
        ["on_hand_qty", "safety_stock_qty", "reorder_point_qty", "allocated_qty"],
    )
    synthetic_values = _read_pair_value_map(
        synthetic_path,
        ["on_hand_qty", "safety_stock_qty", "reorder_point_qty", "allocated_qty"],
    ) if synthetic_path.exists() else {}
    product_ids = _read_id_set(products_path, "product_id")
    location_ids = _read_id_set(locations_path, "location_id")

    inventory_product_ids = {product_id for product_id, _ in inventory_pairs}
    inventory_location_ids = {location_id for _, location_id in inventory_pairs}

    missing_product_ids = sorted(inventory_product_ids - product_ids)
    missing_location_ids = sorted(inventory_location_ids - location_ids)
    missing_context_pairs = sorted(inventory_pairs - context_pairs)
    orphan_context_pairs = sorted(context_pairs - inventory_pairs)

    consistency_issues: List[Dict[str, object]] = []
    for key in sorted(set(inventory_values) & set(synthetic_values)):
        inventory_entry = inventory_values[key]
        synthetic_entry = synthetic_values[key]
        for field in ["on_hand_qty", "safety_stock_qty", "reorder_point_qty", "allocated_qty"]:
            inventory_value = inventory_entry.get(field)
            synthetic_value = synthetic_entry.get(field)
            if inventory_value is None or synthetic_value is None:
                continue
            if abs(inventory_value - synthetic_value) > 1e-6:
                consistency_issues.append(
                    {
                        "product_id": key[0],
                        "location_id": key[1],
                        "field": field,
                        "inventory_value": inventory_value,
                        "synthetic_value": synthetic_value,
                    }
                )

    coverage_ratio = 1.0
    if inventory_pairs:
        coverage_ratio = round(len(inventory_pairs & context_pairs) / len(inventory_pairs), 4)

    return {
        "root_dir": str(root),
        "inventory_pairs_total": len(inventory_pairs),
        "context_pairs_total": len(context_pairs),
        "covered_pairs_total": len(inventory_pairs & context_pairs),
        "coverage_ratio": coverage_ratio,
        "missing_context_pairs": missing_context_pairs,
        "orphan_context_pairs": orphan_context_pairs,
        "missing_product_ids": missing_product_ids,
        "missing_location_ids": missing_location_ids,
        "consistency_issues": consistency_issues,
        "consistency_issue_count": len(consistency_issues),
        "status": (
            "pass"
            if not missing_context_pairs
            and not orphan_context_pairs
            and not missing_product_ids
            and not missing_location_ids
            and not consistency_issues
            else "warning"
        ),
    }


def main() -> int:
    report = generate_product_location_consistency_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
