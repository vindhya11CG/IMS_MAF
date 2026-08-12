import csv
from pathlib import Path

from utils.product_location_validation import generate_product_location_consistency_report


def _write_csv(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_generate_product_location_consistency_report(tmp_path: Path):
    _write_csv(
        tmp_path / "db3_csv_export" / "inventory_positions.csv",
        ["product_id", "location_id", "on_hand_qty"],
        [
            {"product_id": "1", "location_id": "1", "on_hand_qty": "10"},
            {"product_id": "2", "location_id": "2", "on_hand_qty": "5"},
        ],
    )
    _write_csv(
        tmp_path / "db2_csv_export" / "products.csv",
        ["product_id"],
        [{"product_id": "1"}, {"product_id": "2"}],
    )
    _write_csv(
        tmp_path / "db1_csv_export" / "locations.csv",
        ["location_id"],
        [{"location_id": "1"}, {"location_id": "2"}],
    )
    _write_csv(
        tmp_path / "db6_csv_export" / "demand_context_fact.csv",
        ["product_id", "location_id", "weather_demand_multiplier"],
        [
            {"product_id": "1", "location_id": "1", "weather_demand_multiplier": "1.20"},
            {"product_id": "2", "location_id": "2", "weather_demand_multiplier": "1.10"},
        ],
    )

    report = generate_product_location_consistency_report(tmp_path)

    assert report["inventory_pairs_total"] == 2
    assert report["context_pairs_total"] == 2
    assert report["missing_context_pairs"] == []
    assert report["orphan_context_pairs"] == []
    assert report["missing_product_ids"] == []
    assert report["missing_location_ids"] == []
    assert report["consistency_issue_count"] == 0
    assert report["coverage_ratio"] == 1.0
