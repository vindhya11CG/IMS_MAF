import pandas as pd
import glob
import os

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
states = load_csv("data/csv_exports/db1_csv_export/states.csv")

# Standardize keys
if 'sku_id' in daily_snapshots.columns:
    daily_snapshots = daily_snapshots.rename(columns={'sku_id': 'product_id'})
if 'sku_id' in inventory_events.columns:
    inventory_events = inventory_events.rename(columns={'sku_id': 'product_id'})

# Aggregate event and snapshot data to avoid cartesian explosion (just taking most recent/sum for simplicity)
if daily_snapshots is not None:
    daily_snapshots = daily_snapshots.drop_duplicates(subset=['product_id', 'location_id'], keep='last')
if inventory_events is not None:
    inventory_events = inventory_events.drop_duplicates(subset=['product_id', 'location_id'], keep='last')
if in_transit is not None:
    in_transit = in_transit.groupby(['product_id', 'destination_location_id']).sum(numeric_only=True).reset_index()

merged = inventory_positions.copy()

# Base product and category details
merged = merged.merge(products, on='product_id', how='left')
merged = merged.merge(categories, on='category_id', how='left')
merged = merged.merge(velocity, on='velocity_class_id', how='left')
merged = merged.merge(suppliers, on='supplier_id', how='left')

# Locations
merged = merged.merge(locations, on='location_id', how='left')
merged = merged.merge(states, left_on='state_id', right_on='state_code', how='left')

# DC and Stores
merged = merged.merge(distribution_centers, left_on='location_id', right_on='dc_id', how='left', suffixes=('', '_dc'))
# Not all locations are stores, join by location_name or just skip store specifics if no common key. 
# Usually location_id == store_id but let's try store_code
if 'store_code' in stores.columns and 'location_name' in merged.columns:
    pass # we'll just merge what we can
merged = merged.merge(stores, left_on='location_id', right_on='store_id', how='left', suffixes=('', '_store'))

# Climate & Festivals
merged = merged.merge(climate, on='location_id', how='left')
# Festivals might be multiple per location, take first
festivals_dedup = festivals.drop_duplicates(subset=['location_id'])
merged = merged.merge(festivals_dedup, on='location_id', how='left')

# Demand context
demand_dedup = demand_context.drop_duplicates(subset=['product_id', 'location_id'])
merged = merged.merge(demand_dedup, on=['product_id', 'location_id'], how='left')

# Seasonal
if 'season' in merged.columns and 'season_name' in seasonal.columns:
    merged = merged.merge(seasonal, left_on='season', right_on='season_name', how='left')

# In-transit, snapshots, events
in_transit = in_transit.rename(columns={'destination_location_id': 'location_id'})
merged = merged.merge(in_transit[['product_id', 'location_id', 'quantity_in_transit']], on=['product_id', 'location_id'], how='left')

merged = merged.merge(daily_snapshots, on=['product_id', 'location_id'], how='left', suffixes=('', '_snap'))
merged = merged.merge(inventory_events, on=['product_id', 'location_id'], how='left', suffixes=('', '_event'))

# Reorder columns to put main ones first
cols = merged.columns.tolist()
first_cols = ['product_id', 'product_name', 'location_id', 'location_name', 'region_id', 'on_hand_qty']
for c in first_cols:
    if c in cols:
        cols.remove(c)
final_cols = first_cols + cols
merged = merged[final_cols]

output_path = "data/csv_exports/master_full_features.csv"
merged.to_csv(output_path, index=False)

md_table = merged.head(100).to_html(index=False)
with open("sample_table.html", "w", encoding='utf-8') as f:
    f.write(md_table)

print(f"Merge complete. Columns: {len(merged.columns)}")
