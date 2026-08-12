from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple


def _parse_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_int(value: object) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def build_augmented_training_dataset(
    synthetic_path: Path = Path("synthetic_inventory_weather_region_v2_festival_demand.csv"),
    context_path: Path = Path("data/csv_exports/db6_csv_export/demand_context_fact.csv"),
    output_path: Path = Path("data/augmented/augmented_festival_demand_dataset.csv"),
) -> Path:
    with synthetic_path.open("r", encoding="utf-8-sig", newline="") as handle:
        synthetic_rows = list(csv.DictReader(handle))

    context_lookup: Dict[Tuple[int, int], Dict[str, str]] = {}
    if context_path.exists():
        with context_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = (_parse_int(row.get("product_id") or row.get("sku_id")), _parse_int(row.get("location_id")))
                if key not in context_lookup:
                    context_lookup[key] = row

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(synthetic_rows[0].keys()) if synthetic_rows else []
    fieldnames = fieldnames + ["context_adjusted_daily_demand", "context_adjusted_weather_multiplier"]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in synthetic_rows:
            product_id = _parse_int(row.get("product_id") or row.get("sku_id"))
            location_id = _parse_int(row.get("location_id"))
            context_row = context_lookup.get((product_id, location_id), {})

            base_daily_demand = _parse_float(row.get("daily_demand"))
            weather_multiplier = _parse_float(context_row.get("weather_demand_multiplier")) or _parse_float(row.get("weather_demand_multiplier")) or 1.0
            festival_proximity = _parse_float(context_row.get("festival_proximity_score")) or _parse_float(row.get("festival_proximity_score")) or 0.0
            festival_flag = 1 if str(context_row.get("is_festival_day", "0")).strip() in {"1", "True", "true"} else 0
            shopping_flag = 1 if str(context_row.get("is_shopping_season", "0")).strip() in {"1", "True", "true"} else 0
            adjusted_demand = base_daily_demand * weather_multiplier * (1.0 + festival_proximity * 0.6) * (1.0 + festival_flag * 0.25) * (1.0 + shopping_flag * 0.15)
            row["context_adjusted_daily_demand"] = f"{adjusted_demand:.2f}"
            row["context_adjusted_weather_multiplier"] = f"{weather_multiplier:.2f}"
            writer.writerow(row)

    return output_path


if __name__ == "__main__":
    output_path = build_augmented_training_dataset()
    print(f"Wrote augmented training data to {output_path}")
