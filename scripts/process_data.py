import pandas as pd
import glob
import os

print("Checking for inconsistencies...")

def load_csv(path):
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

# Load required tables
inventory_positions = load_csv("data/csv_exports/db3_csv_export/inventory_positions.csv")
products = load_csv("data/csv_exports/db2_csv_export/products.csv")
locations = load_csv("data/csv_exports/db1_csv_export/locations.csv")
distribution_centers = load_csv("data/csv_exports/db1_csv_export/distribution_centers.csv")
stores = load_csv("data/csv_exports/db1_csv_export/stores.csv")
states = load_csv("data/csv_exports/db1_csv_export/states.csv")
categories = load_csv("data/csv_exports/db2_csv_export/product_categories.csv")
velocity = load_csv("data/csv_exports/db2_csv_export/velocity_classes.csv")
suppliers = load_csv("data/csv_exports/db4_csv_export/suppliers.csv")
in_transit = load_csv("data/csv_exports/db3_csv_export/in_transit_inventory.csv")
daily_snapshots = load_csv("data/csv_exports/db5_csv_export/inventory_daily_snapshots.csv")
inventory_events = load_csv("data/csv_exports/db5_csv_export/inventory_events.csv")
demand_context = load_csv("data/csv_exports/db6_csv_export/demand_context_fact.csv")
festivals = load_csv("data/csv_exports/db6_csv_export/festival_calendar.csv")
climate = load_csv("data/csv_exports/db6_csv_export/location_climate_profile.csv")
seasonal = load_csv("data/csv_exports/db2_csv_export/seasonal_patterns.csv")

# Quick Inconsistency checks
print("\n--- INCONSISTENCY CHECKS ---")
missing_products = inventory_positions[~inventory_positions['product_id'].isin(products['product_id'])]
if not missing_products.empty:
    print(f"Found {len(missing_products)} inventory positions with missing product_ids in products table.")

missing_locations = inventory_positions[~inventory_positions['location_id'].isin(locations['location_id'])]
if not missing_locations.empty:
    print(f"Found {len(missing_locations)} inventory positions with missing location_ids in locations table.")

# Rename for consistency
if 'sku_id' in daily_snapshots.columns:
    daily_snapshots = daily_snapshots.rename(columns={'sku_id': 'product_id'})
if 'sku_id' in inventory_events.columns:
    inventory_events = inventory_events.rename(columns={'sku_id': 'product_id'})

print("\n--- JOINING TABLES ---")
# Start with inventory positions as base
merged = inventory_positions.copy()

# 1. Join Products & its dimensions
merged = merged.merge(products, on='product_id', how='left')
merged = merged.merge(categories, on='category_id', how='left')
merged = merged.merge(velocity, on='velocity_class_id', how='left')
merged = merged.merge(suppliers, on='supplier_id', how='left')

# 2. Join Locations & its dimensions
merged = merged.merge(locations, on='location_id', how='left')
merged = merged.merge(states, left_on='state_id', right_on='state_code', how='left')

# 3. Connect to specific location types if needed
merged = merged.merge(distribution_centers[['dc_id', 'region_code']], left_on='location_id', right_on='dc_id', how='left', suffixes=('', '_dc'))

# 4. Join Climate & Demand context
merged = merged.merge(climate, on='location_id', how='left')

print(f"Final merged shape: {merged.shape}")
print("Columns:", merged.columns.tolist())

# Save to CSV
output_path = "data/csv_exports/merged_inventory_master.csv"
merged.to_csv(output_path, index=False)
print(f"\nMerged dataset saved to {output_path}")
print("Top 5 rows:")
print(merged[['product_name', 'location_name', 'region_id', 'on_hand_qty']].head())
