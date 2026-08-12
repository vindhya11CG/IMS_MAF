"""
Data Preparation Module for Demand Forecasting
Handles data loading, cleaning, and feature engineering for synthetic_inventory_weather_region_v2_festival_demand.csv
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Make the demand_forecast_agent package importable when this script is
# run directly from within training_models/ (repo root = parent dir).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from demand_forecast_agent.services.feature_engineering_service import (
    FeatureEngineeringService,
)

DEFAULT_CSV_NAME = "synthetic_inventory_weather_region_v2_festival_demand.csv"


class DataPreparation:
    def __init__(self, csv_path=None):
        self.csv_path = csv_path or os.getenv(
            "TRAINING_DATA_PATH",
            os.path.join(os.path.dirname(__file__), "..", DEFAULT_CSV_NAME),
        )
        self.df = None
        self.df_clean = None
        self.engineer = FeatureEngineeringService()

    def load_data(self):
        """Load CSV with proper data type handling"""
        print("[LOAD] Reading CSV file...")
        self.df = pd.read_csv(self.csv_path)
        print(f"[OK] Loaded {len(self.df):,} records")
        print(f"[OK] Date range: {self.df['date'].min()} to {self.df['date'].max()}")
        return self

    def explore_data(self):
        """Data exploration and quality checks"""
        print("\n[EXPLORE] Data Structure:")
        print(f"Shape: {self.df.shape}")
        print(f"\nColumns: {list(self.df.columns)}")
        print(f"\nMissing values:\n{self.df.isnull().sum()[self.df.isnull().sum() > 0]}")
        print("\nBasic statistics:")
        cols = [c for c in ["daily_demand", "on_hand_qty", "avg_retail_price"] if c in self.df.columns]
        print(self.df[cols].describe())
        return self

    def clean_data(self):
        """Data cleaning and validation"""
        print("\n[CLEAN] Cleaning data...")

        # Convert date column
        self.df["date"] = pd.to_datetime(self.df["date"])

        # Remove duplicates
        before = len(self.df)
        self.df = self.df.drop_duplicates()
        print(f"[OK] Removed {before - len(self.df)} duplicate rows")

        # Ensure calendar & weekend columns
        self.df["day_of_week"] = self.df["date"].dt.dayofweek
        self.df["week_of_year"] = self.df["date"].dt.isocalendar().week.astype(int)
        self.df["is_weekend"] = self.df["day_of_week"].isin([5, 6]).astype(int)

        # Handle missing values
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            missing = self.df[col].isnull().sum()
            if missing > 0:
                self.df[col] = self.df[col].ffill().bfill()
                print(f"[OK] Filled {missing} missing values in {col}")

        # Ensure positive demands
        self.df["daily_demand"] = self.df["daily_demand"].clip(lower=0)

        # Convert boolean/string flag columns to int
        _bool_cols = [
            "heatwave_flag", "coldwave_flag", "monsoon_flag",
            "heavy_rain_flag", "snowfall_flag", "extreme_weather_flag",
            "is_festival_day", "is_shopping_season", "is_promotional"
        ]
        for col in _bool_cols:
            if col in self.df.columns:
                self.df[f"{col}_int"] = (
                    self.df[col]
                    .astype(str)
                    .str.lower()
                    .isin(["true", "1", "yes"])
                    .astype(int)
                )

        self.df_clean = self.df.copy()
        print("[OK] Data cleaned and validated")
        return self

    def feature_engineering(self):
        """Create model features using the SHARED FeatureEngineeringService"""
        print("\n[FEATURES] Engineering features...")

        self.df_clean = self.engineer.execute(self.df_clean)

        # Exploratory lag/rolling features per product
        self.df_clean = self.df_clean.sort_values(["product_id", "date"])
        for lag in [1, 7, 14, 30]:
            self.df_clean[f"demand_lag_{lag}"] = self.df_clean.groupby("product_id")[
                "daily_demand"
            ].shift(lag)
        for window in [7, 14, 30]:
            self.df_clean[f"demand_rolling_mean_{window}"] = (
                self.df_clean.groupby("product_id")["daily_demand"]
                .transform(lambda x: x.rolling(window=window, min_periods=1).mean())
            )

        print(f"[OK] Created temporal + inventory + exploratory features")
        print(f"[OK] Total columns: {len(self.df_clean.columns)}")
        print(f"[OK] Model feature count: {len(FeatureEngineeringService.MODEL_FEATURES)}")
        return self

    def create_train_val_test_splits(self, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15):
        """Time-series aware split to prevent data leakage"""
        print("\n[SPLIT] Creating train/val/test splits...")

        self.df_clean = self.df_clean.sort_values("date").reset_index(drop=True)

        n = len(self.df_clean)
        train_size = int(n * train_ratio)
        val_size = int(n * val_ratio)

        train_end = train_size
        val_end = train_size + val_size

        self.train_df = self.df_clean.iloc[:train_end].copy()
        self.val_df = self.df_clean.iloc[train_end:val_end].copy()
        self.test_df = self.df_clean.iloc[val_end:].copy()

        print(f"[OK] Train: {len(self.train_df):,} records ({train_ratio*100:.0f}%)")
        print(f"[OK] Validation: {len(self.val_df):,} records ({val_ratio*100:.0f}%)")
        print(f"[OK] Test: {len(self.test_df):,} records ({test_ratio*100:.0f}%)")

        return self

    def get_summary_stats(self):
        """Summary statistics for reporting"""
        stats = {
            "total_records": len(self.df_clean),
            "date_range_start": str(self.df_clean["date"].min()),
            "date_range_end": str(self.df_clean["date"].max()),
            "unique_products": self.df_clean["product_id"].nunique(),
            "unique_categories": self.df_clean["category_id"].nunique(),
            "unique_locations": self.df_clean["location_id"].nunique(),
            "avg_daily_demand": round(float(self.df_clean["daily_demand"].mean()), 2),
            "std_daily_demand": round(float(self.df_clean["daily_demand"].std()), 2),
            "min_daily_demand": float(self.df_clean["daily_demand"].min()),
            "max_daily_demand": float(self.df_clean["daily_demand"].max()),
        }
        return stats


def main():
    print("=" * 70)
    print("INVENTORY DEMAND FORECASTING - DATA PREPARATION")
    print("=" * 70)

    dp = DataPreparation()
    (dp.load_data().explore_data().clean_data().feature_engineering().create_train_val_test_splits())

    stats = dp.get_summary_stats()
    print("\n" + "=" * 70)
    print("DATA SUMMARY")
    print("=" * 70)
    for key, value in stats.items():
        print(f"{key:.<40} {value}")

    out_dir = os.path.dirname(__file__)
    print("\n[SAVE] Saving processed datasets...")
    dp.df_clean.to_pickle(os.path.join(out_dir, "data_clean.pkl"))
    dp.train_df.to_pickle(os.path.join(out_dir, "train_data.pkl"))
    dp.val_df.to_pickle(os.path.join(out_dir, "val_data.pkl"))
    dp.test_df.to_pickle(os.path.join(out_dir, "test_data.pkl"))
    print("[OK] All data saved (pickle format)")

    return dp


if __name__ == "__main__":
    dp = main()
