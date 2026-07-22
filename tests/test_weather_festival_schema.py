from pathlib import Path

from utils.csv_loader import CsvInventoryDataLoader


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
    assert rows[0]["temperature_c"] == 17.8
    assert rows[0]["humidity_pct"] == 58.0
    assert rows[0]["weather_severity_index"] == 0.23
    assert rows[0]["is_festival_day"] is True
    assert rows[0]["days_to_next_festival"] == 11.0
    assert rows[0]["festival_proximity_score"] == 0.65
    assert rows[0]["is_shopping_season"] is True
