import pandas as pd
import numpy as np

def smart_impute(file_path):
    print(f"Loading {file_path}...")
    df = pd.read_csv(file_path)
    
    # 1. Fill numeric columns with the median of their respective 'category_id' if available
    num_cols = df.select_dtypes(include=[np.number]).columns
    
    if 'category_id' in df.columns:
        for col in num_cols:
            if df[col].isna().any():
                # Fill with median of the category group
                df[col] = df.groupby('category_id')[col].transform(lambda x: x.fillna(x.median()))
                
    # Fallback to global median for any remaining NaNs in numeric columns
    for col in num_cols:
        if df[col].isna().any():
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val if not pd.isna(median_val) else 0)

    # 2. Fill categorical columns with the mode (most frequent value) of their 'category_id'
    cat_cols = df.select_dtypes(include=['object', 'bool']).columns
    
    if 'category_id' in df.columns:
        for col in cat_cols:
            if df[col].isna().any():
                df[col] = df.groupby('category_id')[col].transform(
                    lambda x: x.fillna(x.mode()[0] if not x.mode().empty else 'Unknown')
                )
                
    # Fallback to global mode
    for col in cat_cols:
        if df[col].isna().any():
            mode_val = df[col].mode()
            df[col] = df[col].fillna(mode_val[0] if not mode_val.empty else 'Unknown')
            
    print(f"Missing values remaining: {df.isna().sum().sum()}")
    df.to_csv(file_path, index=False)
    print(f"Smart imputation complete for {file_path}")

smart_impute("data/csv_exports/master_full_features.csv")
smart_impute("data/csv_exports/merged_inventory_master.csv")
