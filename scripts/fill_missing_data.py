import pandas as pd
import numpy as np

def fill_missing(file_path):
    print(f"Processing {file_path}...")
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return

    # Count missing before
    missing_before = df.isna().sum().sum()
    print(f"Total missing values before: {missing_before}")

    if missing_before == 0:
        print("No missing values found.")
        return

    # Fill numerical columns
    num_cols = df.select_dtypes(include=[np.number]).columns
    # For inventory/qty/prices, filling with 0 is often safest if they are missing
    df[num_cols] = df[num_cols].fillna(0)

    # Fill categorical/object columns
    cat_cols = df.select_dtypes(include=['object', 'bool']).columns
    df[cat_cols] = df[cat_cols].fillna('Unknown')

    # Count missing after
    missing_after = df.isna().sum().sum()
    print(f"Total missing values after: {missing_after}")

    # Save back to the same file
    df.to_csv(file_path, index=False)
    print(f"Successfully updated {file_path}\n")

files_to_process = [
    "data/csv_exports/master_full_features.csv",
    "data/csv_exports/merged_inventory_master.csv"
]

for f in files_to_process:
    fill_missing(f)
