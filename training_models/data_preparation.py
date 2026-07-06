"""
Data Preparation Module for Demand Forecasting
Handles data loading, cleaning, and feature engineering

FIXES APPLIED (vs. the original file):

1. Column names now match the real dataset / DB schema. The original file
   referenced columns that don't exist anywhere in the system:
       item_id            -> product_id          (matches products.sku_id / CSV)
       storage_location_id-> location_id          (matches locations/inventory_positions)
       stock_level        -> on_hand_qty          (matches inventory_positions)
       unit_price         -> avg_retail_price     (matches CSV / products.retail_price)
       reorder_point      -> reorder_point_qty    (matches inventory_positions)
       category (string)  -> category_id (numeric, already in the CSV/DB - no
                              re-encoding needed, see #3 below)
       item_popularity_score -> does not exist anywhere; velocity is instead
                              taken directly from velocity_class_id, which the
                              dataset already provides.

2. Hardcoded input filename `synthetic_inventory.csv` did not match the
   real file `synthetic_inventory_db_native.csv`. Now configurable via the
   `csv_path` constructor arg / `TRAINING_DATA_PATH` env var, defaulting to
   the real filename.

3. Category encoding used to be `{cat: idx for idx, cat in enumerate(df['category'].unique())}`
   - built fresh from whatever order categories happened to appear in in a
   given run. That is non-deterministic across separate training runs (and
   meaningless at inference, which sees one row at a time). The dataset
   already has a stable numeric `category_id` from the DB schema
   (product_categories.category_id), so it's used directly instead.

4. Feature engineering (stock_gap, available_stock, safety_ratio,
   velocity_score, temporal features, is_promotional_int) is now delegated
   to `demand_forecast_agent.services.feature_engineering_service.FeatureEngineeringService`
   - the SAME class the live agent uses at inference. This is what keeps
   training and inference features from drifting apart again in the future.

5. Lag/rolling features are still computed here for exploratory analysis
   (`explore_data`/plots), but are no longer fed to the deployed model,
   since a live single-row inference request has no history to compute
   them from. See training_models/model_training.py for the fixed model
   feature list.
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

DEFAULT_CSV_NAME = "synthetic_inventory_db_native.csv"


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
        print(f"\u2713 Loaded {len(self.df):,} records")
        print(f"\u2713 Date range: {self.df['date'].min()} to {self.df['date'].max()}")
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
        print(f"\u2713 Removed {before - len(self.df)} duplicate rows")

        # Handle missing values
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            missing = self.df[col].isnull().sum()
            if missing > 0:
                self.df[col] = self.df[col].ffill().bfill()
                print(f"\u2713 Filled {missing} missing values in {col}")

        # Ensure positive demands
        self.df["daily_demand"] = self.df["daily_demand"].clip(lower=0)

        # Remove outliers (demands > 5 std devs from mean per product)
        for product in self.df["product_id"].unique():
            mask = self.df["product_id"] == product
            demand_data = self.df.loc[mask, "daily_demand"]
            if len(demand_data) > 0:
                mean = demand_data.mean()
                std = demand_data.std()
                if std > 0:
                    outlier_threshold = mean + (5 * std)
                    # NOTE: daily_demand is int64. clip(upper=<float>) produces
                    # float64 results, and newer pandas (this project sees
                    # pandas 2.x/3.x) raises LossySetitemError rather than
                    # silently downcasting when you assign floats back into
                    # an int64 column via .loc. Round + cast explicitly so
                    # the dtype stays consistent either way.
                    clipped = (
                        self.df.loc[mask, "daily_demand"]
                        .clip(upper=outlier_threshold)
                        .round()
                        .astype(self.df["daily_demand"].dtype)
                    )
                    self.df.loc[mask, "daily_demand"] = clipped

        self.df_clean = self.df.copy()
        print("\u2713 Data cleaned and validated")
        return self

    def feature_engineering(self):
        """Create model features using the SHARED FeatureEngineeringService
        (the same class used at inference time), plus exploratory-only
        lag/rolling features that are not fed to the deployed model."""
        print("\n[FEATURES] Engineering features...")

        self.df_clean = self.engineer.execute(self.df_clean)

        # Exploratory-only lag/rolling features (per product). NOT part of
        # FeatureEngineeringService.MODEL_FEATURES, so they are never sent
        # to the model - a single inference request has no history to
        # compute these from, so training the model on them would create
        # exactly the train/inference skew this fix is meant to eliminate.
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

        print(f"\u2713 Created temporal + inventory + exploratory lag/rolling features")
        print(f"\u2713 Total columns now: {len(self.df_clean.columns)}")
        print(f"\u2713 Model-facing feature columns: {FeatureEngineeringService.MODEL_FEATURES}")
        return self

    def create_train_val_test_splits(self, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15):
        """
        Time-series aware split to prevent data leakage
        70% train, 15% val, 15% test
        """
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

        print(f"\u2713 Train: {len(self.train_df):,} records ({train_ratio*100:.0f}%)")
        print(f"\u2713 Validation: {len(self.val_df):,} records ({val_ratio*100:.0f}%)")
        print(f"\u2713 Test: {len(self.test_df):,} records ({test_ratio*100:.0f}%)")

        return self

    def get_item_location_series(self, product_id, location_id=None):
        """Extract time series for a specific product (and location if specified)"""
        if location_id:
            mask = (self.df_clean["product_id"] == product_id) & (
                self.df_clean["location_id"] == location_id
            )
        else:
            mask = self.df_clean["product_id"] == product_id

        series = self.df_clean[mask].sort_values("date")[["date", "daily_demand"]].reset_index(
            drop=True
        )
        return series

    def get_summary_stats(self):
        """Summary statistics for reporting"""
        stats = {
            "total_records": len(self.df_clean),
            "date_range_start": self.df_clean["date"].min(),
            "date_range_end": self.df_clean["date"].max(),
            "unique_products": self.df_clean["product_id"].nunique(),
            "unique_categories": self.df_clean["category_id"].nunique(),
            "unique_locations": self.df_clean["location_id"].nunique(),
            "avg_daily_demand": self.df_clean["daily_demand"].mean(),
            "std_daily_demand": self.df_clean["daily_demand"].std(),
            "min_daily_demand": self.df_clean["daily_demand"].min(),
            "max_daily_demand": self.df_clean["daily_demand"].max(),
        }
        return stats


def main():
    """Main execution"""
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
        if isinstance(value, float):
            print(f"{key:.<40} {value:.2f}")
        else:
            print(f"{key:.<40} {value}")

    out_dir = os.path.dirname(__file__)
    print("\n[SAVE] Saving processed datasets...")
    # NOTE: switched from .to_parquet()/.read_parquet() to
    # .to_pickle()/.read_pickle(). Parquet requires the `pyarrow` or
    # `fastparquet` package, and NEITHER is listed in requirements.txt -
    # so the original code would fail with an ImportError the first time
    # it tried to save, even in the real environment. Pickle needs no
    # extra dependency and preserves dtypes exactly (important for the
    # `date` column).
    dp.df_clean.to_pickle(os.path.join(out_dir, "data_clean.pkl"))
    dp.train_df.to_pickle(os.path.join(out_dir, "train_data.pkl"))
    dp.val_df.to_pickle(os.path.join(out_dir, "val_data.pkl"))
    dp.test_df.to_pickle(os.path.join(out_dir, "test_data.pkl"))
    print("\u2713 All data saved (pickle format)")

    return dp


if __name__ == "__main__":
    dp = main()
