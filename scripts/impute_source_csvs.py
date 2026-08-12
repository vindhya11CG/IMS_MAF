import pandas as pd
import numpy as np
import glob
import os

def impute_file(file_path):
    print(f"Processing {file_path}...")
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return

    missing_before = df.isna().sum().sum()
    if missing_before == 0:
        return

    # Impute Numeric with Median
    num_cols = df.select_dtypes(include=[np.number]).columns
    for col in num_cols:
        if df[col].isna().any():
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val if not pd.isna(median_val) else 0)

    # Impute Categorical with Mode
    cat_cols = df.select_dtypes(include=['object', 'bool']).columns
    for col in cat_cols:
        if df[col].isna().any():
            mode_val = df[col].mode()
            df[col] = df[col].fillna(mode_val[0] if not mode_val.empty else 'Unknown')
            
    df.to_csv(file_path, index=False)
    print(f"Filled {missing_before} missing values in {file_path}")

csv_files = glob.glob('data/csv_exports/db*/*.csv')
for f in csv_files:
    impute_file(f)
