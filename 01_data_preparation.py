"""
Data Preparation Module for Demand Forecasting
Handles data loading, cleaning, and feature engineering
"""
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class DataPreparation:
    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.df = None
        self.df_clean = None
        
    def load_data(self):
        """Load CSV with proper data type handling"""
        print("[LOAD] Reading CSV file...")
        self.df = pd.read_csv(self.csv_path)
        print(f"✓ Loaded {len(self.df):,} records")
        print(f"✓ Date range: {self.df['date'].min()} to {self.df['date'].max()}")
        return self
    
    def explore_data(self):
        """Data exploration and quality checks"""
        print("\n[EXPLORE] Data Structure:")
        print(f"Shape: {self.df.shape}")
        print(f"\nColumns: {list(self.df.columns)}")
        print(f"\nData types:\n{self.df.dtypes}")
        print(f"\nMissing values:\n{self.df.isnull().sum()}")
        print(f"\nBasic statistics:")
        print(self.df[['daily_demand', 'stock_level', 'unit_price']].describe())
        return self
    
    def clean_data(self):
        """Data cleaning and validation"""
        print("\n[CLEAN] Cleaning data...")
        
        # Convert date column
        self.df['date'] = pd.to_datetime(self.df['date'])
        
        # Remove duplicates
        before = len(self.df)
        self.df = self.df.drop_duplicates()
        print(f"✓ Removed {before - len(self.df)} duplicate rows")
        
        # Handle missing values
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            missing = self.df[col].isnull().sum()
            if missing > 0:
                # Forward fill then backward fill
                self.df[col] = self.df[col].fillna(method='ffill').fillna(method='bfill')
                print(f"✓ Filled {missing} missing values in {col}")
        
        # Ensure positive demands
        self.df['daily_demand'] = self.df['daily_demand'].clip(lower=0)
        
        # Remove outliers (demands > 5 std devs from mean per item)
        for item in self.df['item_id'].unique():
            mask = self.df['item_id'] == item
            demand_data = self.df.loc[mask, 'daily_demand']
            if len(demand_data) > 0:
                mean = demand_data.mean()
                std = demand_data.std()
                if std > 0:
                    outlier_threshold = mean + (5 * std)
                    self.df.loc[mask, 'daily_demand'] = self.df.loc[mask, 'daily_demand'].clip(upper=outlier_threshold)
        
        self.df_clean = self.df.copy()
        print(f"✓ Data cleaned and validated")
        return self
    
    def feature_engineering(self):
        """Create additional features for modeling"""
        print("\n[FEATURES] Engineering features...")
        
        # Temporal features
        self.df_clean['year'] = self.df_clean['date'].dt.year
        self.df_clean['month'] = self.df_clean['date'].dt.month
        self.df_clean['quarter'] = self.df_clean['date'].dt.quarter
        self.df_clean['day_of_year'] = self.df_clean['date'].dt.dayofyear
        self.df_clean['week_of_year'] = self.df_clean['date'].dt.isocalendar().week
        
        # Cyclical encoding for month (seasonality)
        self.df_clean['month_sin'] = np.sin(2 * np.pi * self.df_clean['month'] / 12)
        self.df_clean['month_cos'] = np.cos(2 * np.pi * self.df_clean['month'] / 12)
        
        # Categorical encoding
        self.df_clean['is_promotional_int'] = self.df_clean['is_promotional'].astype(int)
        
        # Lag features (per item-location)
        for lag in [1, 7, 14, 30]:
            self.df_clean[f'demand_lag_{lag}'] = (
                self.df_clean.groupby('item_id')['daily_demand'].shift(lag)
            )
        
        # Rolling statistics (per item-location)
        for window in [7, 14, 30]:
            self.df_clean[f'demand_rolling_mean_{window}'] = (
                self.df_clean.groupby('item_id')['daily_demand']
                .transform(lambda x: x.rolling(window=window, min_periods=1).mean())
            )
            self.df_clean[f'demand_rolling_std_{window}'] = (
                self.df_clean.groupby('item_id')['daily_demand']
                .transform(lambda x: x.rolling(window=window, min_periods=1).std().fillna(0))
            )
        
        # Velocity class encoding
        velocity_map = {'A': 3, 'B': 2, 'C': 1}
        if 'item_popularity_score' in self.df_clean.columns:
            self.df_clean['velocity_class'] = pd.cut(
                self.df_clean['item_popularity_score'],
                bins=[0, 0.33, 0.67, 1.0],
                labels=['C', 'B', 'A']
            )
        
        # Category encoding
        category_mapping = {cat: idx for idx, cat in enumerate(self.df_clean['category'].unique())}
        self.df_clean['category_encoded'] = self.df_clean['category'].map(category_mapping)
        
        # Stock status
        self.df_clean['stock_vs_reorder'] = self.df_clean['stock_level'] / (self.df_clean['reorder_point'] + 1)
        self.df_clean['stock_ratio'] = self.df_clean['stock_level'] / (self.df_clean['stock_level'].max() + 1)
        
        print(f"✓ Created temporal, lag, rolling, and categorical features")
        print(f"✓ Total features now: {len(self.df_clean.columns)}")
        return self
    
    def create_train_val_test_splits(self, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15):
        """
        Time-series aware split to prevent data leakage
        70% train, 15% val, 15% test
        """
        print("\n[SPLIT] Creating train/val/test splits...")
        
        # Sort by date
        self.df_clean = self.df_clean.sort_values('date').reset_index(drop=True)
        
        n = len(self.df_clean)
        train_size = int(n * train_ratio)
        val_size = int(n * val_ratio)
        
        # Time-series split (no shuffling to preserve temporal order)
        train_end = train_size
        val_end = train_size + val_size
        
        self.train_df = self.df_clean.iloc[:train_end].copy()
        self.val_df = self.df_clean.iloc[train_end:val_end].copy()
        self.test_df = self.df_clean.iloc[val_end:].copy()
        
        print(f"✓ Train: {len(self.train_df):,} records ({train_ratio*100:.0f}%)")
        print(f"  Date range: {self.train_df['date'].min()} to {self.train_df['date'].max()}")
        print(f"✓ Validation: {len(self.val_df):,} records ({val_ratio*100:.0f}%)")
        print(f"  Date range: {self.val_df['date'].min()} to {self.val_df['date'].max()}")
        print(f"✓ Test: {len(self.test_df):,} records ({test_ratio*100:.0f}%)")
        print(f"  Date range: {self.test_df['date'].min()} to {self.test_df['date'].max()}")
        
        return self
    
    def get_item_location_series(self, item_id, location_id=None):
        """Extract time series for a specific item (and location if specified)"""
        if location_id:
            mask = (self.df_clean['item_id'] == item_id) & (self.df_clean['storage_location_id'] == location_id)
        else:
            mask = self.df_clean['item_id'] == item_id
        
        series = self.df_clean[mask].sort_values('date')[['date', 'daily_demand']].reset_index(drop=True)
        return series
    
    def get_summary_stats(self):
        """Summary statistics for reporting"""
        stats = {
            'total_records': len(self.df_clean),
            'date_range_start': self.df_clean['date'].min(),
            'date_range_end': self.df_clean['date'].max(),
            'unique_items': self.df_clean['item_id'].nunique(),
            'unique_categories': self.df_clean['category'].nunique(),
            'unique_locations': self.df_clean['storage_location_id'].nunique(),
            'avg_daily_demand': self.df_clean['daily_demand'].mean(),
            'std_daily_demand': self.df_clean['daily_demand'].std(),
            'min_daily_demand': self.df_clean['daily_demand'].min(),
            'max_daily_demand': self.df_clean['daily_demand'].max(),
        }
        return stats


def main():
    """Main execution"""
    print("="*70)
    print("INVENTORY DEMAND FORECASTING - DATA PREPARATION")
    print("="*70)
    
    # Initialize
    dp = DataPreparation('synthetic_inventory.csv')
    
    # Execute pipeline
    (dp
     .load_data()
     .explore_data()
     .clean_data()
     .feature_engineering()
     .create_train_val_test_splits())
    
    # Summary
    stats = dp.get_summary_stats()
    print("\n" + "="*70)
    print("DATA SUMMARY")
    print("="*70)
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"{key:.<40} {value:.2f}")
        else:
            print(f"{key:.<40} {value}")
    
    # Save processed data
    print("\n[SAVE] Saving processed datasets...")
    dp.df_clean.to_parquet('data_clean.parquet', index=False)
    dp.train_df.to_parquet('train_data.parquet', index=False)
    dp.val_df.to_parquet('val_data.parquet', index=False)
    dp.test_df.to_parquet('test_data.parquet', index=False)
    print("✓ All data saved to parquet format")
    
    return dp


if __name__ == "__main__":
    dp = main()
