# Weather and Festival Enrichment Schema

This project now supports an enriched demand dataset that adds weather and festival context to the existing inventory model.

## Source file
- [synthetic_inventory_weather_region_v2_festival_demand.csv](synthetic_inventory_weather_region_v2_festival_demand.csv)

## Core idea
The enriched dataset is designed to be joined to the existing inventory tables using business keys:

- inventory product / SKU key: product_id -> sku_id
- inventory location key: location_id
- inventory date key: date (used as the daily observation date)

## Recommended join logic

### 1. Join inventory positions to demand context
Use the enriched file as a daily fact table for demand and risk shaping.

- Left join from inventory positions to the enriched dataset on:
  - location_id
  - product_id / sku_id

This allows the system to enrich a base inventory record with:
- weather conditions such as temperature_c, humidity_pct, rainfall_mm, weather_severity_index
- festival flags such as is_festival_day, festival_proximity_score, is_shopping_season
- derived demand signals such as weather_adjusted_demand and daily_demand_pre_festival_adjustment

### 2. Join daily snapshots to demand context
For daily operational analysis, join the snapshot table to the enriched dataset using:
- snapshot_date = date
- sku_id = product_id
- location_id

This supports day-level analysis of stock movement under weather and festival pressure.

### 3. Join location reference data
To add geography context, join the enriched dataset to location tables using:
- location_id

Optional enrichment from the location master can include:
- city, state_province, country_code
- climate_zone and regional demand indicators already embedded in the enriched file

## Important columns

### Weather-related columns
- temperature_c
- feels_like_c
- humidity_pct
- rainfall_mm
- snowfall_cm
- wind_speed_kmh
- uv_index
- cloud_cover_pct
- pressure_hpa
- visibility_km
- heatwave_flag
- coldwave_flag
- monsoon_flag
- heavy_rain_flag
- snowfall_flag
- extreme_weather_flag
- temperature_deviation
- rainfall_deviation
- weather_severity_index
- weather_demand_multiplier
- weather_supply_risk_score
- climate_anomaly_score
- weather_confidence_score
- weather_adjusted_demand
- weather_adjusted_safety_stock
- weather_adjusted_reorder_point

### Festival-related columns
- is_festival_day
- days_to_next_festival
- days_since_last_festival
- festival_proximity_score
- is_shopping_season
- daily_demand_pre_festival_adjustment

## Suggested logical schema extension
If this data were moved into a relational schema, the following structure would be appropriate:

- inventory_fact: existing stock and movement data
- demand_context_fact: weather, festival, and demand adjustment context
- location_dim: location master data
- product_dim: product / SKU master data

## Notes
- The dataset is additive and does not replace the existing inventory schema.
- Existing inventory calculations remain valid; the new file simply provides richer context for demand forecasting and risk scoring.
