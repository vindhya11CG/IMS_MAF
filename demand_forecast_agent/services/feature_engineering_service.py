"""
FeatureEngineeringService
--------------------------
Single source of truth for feature engineering. It is imported by BOTH:

  1. The training pipeline (training_models/data_preparation.py), which runs
     it in batch over the full historical CSV.
  2. The live agent (demand_forecast_workflow_service.py), which runs it over
     a single-row inference payload coming from an API/service call.

Every feature below is intentionally something computable from a SINGLE ROW
(no lookback needed).

Includes full set of weather, festival, calendar (weekend), location, and
warehouse disruption features for event-driven demand forecasting.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class FeatureEngineeringService:
    """Derives model-ready features from either a raw payload dict
    (single inference request) or a raw historical DataFrame (training)."""

    MODEL_FEATURES = [
        # Calendar & Temporal
        "month", "quarter", "day_of_year", "day_of_week", "week_of_year", "is_weekend",
        "month_sin", "month_cos",
        "is_promotional_int",
        # Inventory & Cost
        "on_hand_qty", "allocated_qty", "safety_stock_qty", "reorder_point_qty",
        "stock_gap", "available_stock", "safety_ratio", "velocity_score",
        "avg_retail_price", "holding_cost_per_unit_day", "handling_cost_per_unit",
        "order_fulfillment_rate", "total_orders_last_month", "turnover_ratio",
        "demand_std_dev", "lead_time_days", "season_multiplier",
        "category_id", "velocity_class_id",
        # Weather Variables
        "temperature_c", "feels_like_c", "humidity_pct", "rainfall_mm", "snowfall_cm",
        "wind_speed_kmh", "pressure_hpa", "weather_demand_multiplier", "weather_severity_index",
        "climate_anomaly_score",
        # Weather Flags (numeric)
        "heatwave_flag_int", "coldwave_flag_int", "monsoon_flag_int",
        "heavy_rain_flag_int", "snowfall_flag_int", "extreme_weather_flag_int",
        # Festival & Shopping Season
        "is_festival_day_int", "days_to_next_festival", "days_since_last_festival",
        "festival_proximity_score", "is_shopping_season_int",
        # Location, Demographics & Warehouse
        "population_index", "income_index", "urbanization_score",
        "regional_demand_index", "consumer_spending_index", "weather_sensitivity_score",
        "logistics_complexity_score", "distance_to_dc_km", "regional_supply_risk_score",
        "supply_disruption_risk",
    ]

    _country_cache = {}

    @classmethod
    def _get_country_code(cls, location_id) -> str:
        if not location_id or pd.isna(location_id):
            return "US"
        loc_id = int(location_id)
        if not cls._country_cache:
            states_map = {}
            try:
                import csv
                from pathlib import Path
                root = Path(__file__).parent.parent.parent / "data" / "csv_exports"
                if not root.exists():
                    root = Path("data/csv_exports")
                
                states_path = root / "db1_csv_export" / "states.csv"
                locations_path = root / "db1_csv_export" / "locations.csv"
                
                if states_path.exists() and locations_path.exists():
                    with open(states_path, "r", encoding="utf-8-sig") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            s_id = row.get("state_id")
                            s_code = row.get("state_code", "")
                            if s_id:
                                states_map[int(s_id)] = s_code
                    
                    with open(locations_path, "r", encoding="utf-8-sig") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            l_id = row.get("location_id")
                            s_id = row.get("state_id")
                            if l_id and s_id:
                                s_code = states_map.get(int(s_id), "")
                                country = "US"
                                if "-" in s_code:
                                    parts = s_code.split("-")
                                    if parts[0].upper() in {"IN", "SE", "US"}:
                                        country = parts[0].upper()
                                cls._country_cache[int(l_id)] = country
            except Exception:
                pass
        return cls._country_cache.get(loc_id, "US")

    @classmethod
    def _get_holiday_dates(cls, country_code: str, year: int) -> frozenset:
        if country_code not in ["US", "IN", "SE"]:
            return frozenset()
        try:
            import holidays as holidays_lib
            raw = holidays_lib.country_holidays(country_code, years=[year - 1, year, year + 1])
            _PURE_WEEKDAY_FLAG_NAMES = {"söndag", "sunday"}
            cleaned = {d: name for d, name in raw.items() if name.strip().lower() not in _PURE_WEEKDAY_FLAG_NAMES}
            return frozenset(cleaned.keys())
        except Exception:
            return frozenset()

    @classmethod
    def _compute_row_festivals(cls, row_date, country_code: str):
        import datetime
        if not row_date or pd.isna(row_date):
            row_date = datetime.date.today()
        elif isinstance(row_date, str):
            try:
                row_date = pd.to_datetime(row_date).date()
            except Exception:
                row_date = datetime.date.today()
        elif hasattr(row_date, "date"):
            row_date = row_date.date()
        elif not isinstance(row_date, datetime.date):
            row_date = datetime.date.today()

        year = row_date.year
        holiday_dates = cls._get_holiday_dates(country_code, year)
        
        LOOKAHEAD_CAP = 30.0
        
        if not holiday_dates:
            days_to_next = LOOKAHEAD_CAP
            days_since_last = LOOKAHEAD_CAP
        else:
            future = [(d - row_date).days for d in holiday_dates if d >= row_date]
            past = [(row_date - d).days for d in holiday_dates if d <= row_date]
            days_to_next = min(future) if future else LOOKAHEAD_CAP
            days_since_last = min(past) if past else LOOKAHEAD_CAP
            
        days_to_next = float(min(days_to_next, LOOKAHEAD_CAP))
        days_since_last = float(min(days_since_last, LOOKAHEAD_CAP))
        
        is_festival_day = 1 if row_date in holiday_dates else 0
        festival_proximity_score = float(np.exp(-min(days_to_next, days_since_last) / 7.0))
        
        _SHOPPING_SEASON_WINDOWS = {
            "US": [(11, 20, 30), (12, 1, 26)],
            "IN": [(10, 1, 31), (11, 1, 15)],
            "SE": [(6, 15, 26), (12, 1, 24)],
        }
        is_shopping_season = 0
        for month, day_start, day_end in _SHOPPING_SEASON_WINDOWS.get(country_code, []):
            if row_date.month == month and day_start <= row_date.day <= day_end:
                is_shopping_season = 1
                break
                
        return is_festival_day, days_to_next, days_since_last, festival_proximity_score, is_shopping_season

    def execute(self, df):

        # Convert dictionary payload to DataFrame
        if isinstance(df, dict):
            df = pd.DataFrame([df])
        elif isinstance(df, pd.DataFrame):
            df = df.copy()
        else:
            raise TypeError(
                "FeatureEngineeringService expects dict or pandas DataFrame."
            )

        # -----------------------
        # Temporal features
        # -----------------------
        if "date" in df.columns:
            parsed_date = pd.to_datetime(df["date"], errors="coerce")
            parsed_date = parsed_date.fillna(pd.Timestamp.now())
        else:
            parsed_date = pd.Series([pd.Timestamp.now()] * len(df), index=df.index)

        df["month"] = parsed_date.dt.month
        df["quarter"] = parsed_date.dt.quarter
        df["day_of_year"] = parsed_date.dt.dayofyear
        if "day_of_week" not in df.columns:
            df["day_of_week"] = parsed_date.dt.dayofweek
        df["week_of_year"] = parsed_date.dt.isocalendar().week.astype(int)
        if "is_weekend" not in df.columns:
            df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

        # -----------------------
        # Inventory gap & ratios
        # -----------------------
        if "on_hand_qty" in df.columns and "reorder_point_qty" in df.columns:
            df["stock_gap"] = df["on_hand_qty"] - df["reorder_point_qty"]

        if "on_hand_qty" in df.columns and "allocated_qty" in df.columns:
            df["available_stock"] = df["on_hand_qty"] - df["allocated_qty"]

        if "safety_stock_qty" in df.columns and "on_hand_qty" in df.columns:
            df["safety_ratio"] = df["safety_stock_qty"] / (df["on_hand_qty"].abs() + 1)

        if "annual_units_max" in df.columns:
            df["velocity_score"] = np.log1p(df["annual_units_max"])

        # Helper for boolean/string to int conversion
        def parse_bool_col(col_name):
            if col_name in df.columns:
                return df[col_name].astype(str).str.lower().isin(["true", "1", "yes"]).astype(int)
            return 0

        # -----------------------
        # Promotional & Event Flags -> numeric
        # -----------------------
        df["is_promotional_int"] = parse_bool_col("is_promotional")

        # Dynamic country and festival feature calculations
        if "country_code" not in df.columns:
            if "location_id" in df.columns:
                df["country_code"] = df["location_id"].apply(self._get_country_code)
            else:
                df["country_code"] = "US"

        is_fest = []
        days_to = []
        days_since = []
        prox = []
        is_shop = []

        for _, row in df.iterrows():
            d = row.get("date")
            cc = row.get("country_code", "US")
            fest_day, d_to, d_since, p_score, shop_season = self._compute_row_festivals(d, cc)
            
            # Allow payload overrides if present
            if "is_festival_day" in row and pd.notna(row["is_festival_day"]):
                val = str(row["is_festival_day"]).lower()
                if val in ["true", "1", "yes"]:
                    fest_day = 1
                elif val in ["false", "0", "no"]:
                    fest_day = 0
            
            if "is_shopping_season" in row and pd.notna(row["is_shopping_season"]):
                val = str(row["is_shopping_season"]).lower()
                if val in ["true", "1", "yes"]:
                    shop_season = 1
                elif val in ["false", "0", "no"]:
                    shop_season = 0

            if "festival_proximity_score" in row and pd.notna(row["festival_proximity_score"]):
                p_score = float(row["festival_proximity_score"])

            if "days_to_next_festival" in row and pd.notna(row["days_to_next_festival"]):
                d_to = float(row["days_to_next_festival"])

            if "days_since_last_festival" in row and pd.notna(row["days_since_last_festival"]):
                d_since = float(row["days_since_last_festival"])

            is_fest.append(fest_day)
            days_to.append(d_to)
            days_since.append(d_since)
            prox.append(p_score)
            is_shop.append(shop_season)

        df["is_festival_day_int"] = is_fest
        df["days_to_next_festival"] = days_to
        df["days_since_last_festival"] = days_since
        df["festival_proximity_score"] = prox
        df["is_shopping_season_int"] = is_shop

        # Weather event flags
        df["heatwave_flag_int"] = parse_bool_col("heatwave_flag")
        df["coldwave_flag_int"] = parse_bool_col("coldwave_flag")
        df["monsoon_flag_int"] = parse_bool_col("monsoon_flag")
        df["heavy_rain_flag_int"] = parse_bool_col("heavy_rain_flag")
        df["snowfall_flag_int"] = parse_bool_col("snowfall_flag")
        df["extreme_weather_flag_int"] = parse_bool_col("extreme_weather_flag")

        return df

    def to_model_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reindex an already-engineered DataFrame onto the fixed
        MODEL_FEATURES column set/order, filling anything missing with 0.
        This is what guarantees train/inference shape parity."""
        return df.reindex(columns=self.MODEL_FEATURES, fill_value=0)
