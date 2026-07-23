# Multi-Region Expansion Guide

## Overview

The Inventory Management System (IMS) has been expanded to natively support global multi-region deployments, starting with the addition of **India (IN)** and **Sweden (SE)** alongside the existing United States (US) region.

This expansion increases the footprint of our inventory monitoring capabilities to **74 total locations (69 stores and 5 distribution centers)** across 28 states/provinces globally.

## Expansion Footprint

### 1. New Locations
**India (10 Stores, 1 Distribution Center)**:
- Stores: Mumbai (Central, FC Road), Delhi, Bangalore, Chennai, Hyderabad, Ahmedabad, Kochi, Jaipur, Kolkata.
- DC: India Hub DC (Mumbai).

**Sweden (9 Stores, 1 Distribution Center)**:
- Stores: Stockholm, Gothenburg, Malmö, Uppsala, Linköping, Örebro, Helsingborg, Umeå, Västerås.
- DC: Sweden Nordic DC (Stockholm).

### 2. New Climate Profiles
We've added 21 new climate profiles tailored for the multi-region locations, capturing varied climate zones:
- **India**: Tropical-Wet, Tropical-Savanna, Semi-Arid, Humid-Subtropical.
- **Sweden**: Humid-Continental, Oceanic, Subarctic.

### 3. Festival & Cultural Context
The `festival_calendar.csv` DB export has been significantly enriched with local holidays that impact demand and supply risk:
- **India**: Diwali, Holi, Eid ul-Fitr, Ganesh Chaturthi, Durga Puja, Independence Day, Republic Day, Makar Sankranti.
- **Sweden**: Midsommar, Nationaldagen, Lucia, Påskdagen, Christmas, Valborg, Kräftskiva.

## Backend Schema Updates

No structural changes were made to the core CSV loading mechanism or database schemas; instead, the data payloads were expanded:
- **`states.csv`**: Added state abbreviations with country prefixes (e.g., `IN-MH`, `SE-AB`).
- **`locations.csv` & `stores.csv`**: Appended store configurations for all new regions.
- **`distribution_centers.csv`**: Appended regional hub DCs.
- **`inventory_positions.csv` & `inventory_daily_snapshots.csv`**: Populated representative daily and core inventory volumes for the new stores.

## Backend Agentic Services

The core agentic services operate identically across all regions without code refactoring. The demand forecast agent processes regional modifiers (such as `regional_demand_index`, `climate_anomaly_score`, and `festival_proximity_score`) automatically from the provided database files via `utils/csv_loader.py`.

## New API Layer (For Frontend Teams)

The system exposes new and enhanced endpoints designed for a multi-region UI:
- `/locations` and `/locations/stores`: Extended `LocationResponse` / `StoreResponse` with derived `country_code`, `country`, `state_name`, and `state_code` fields. Also added `country_code` filters.
- `/regions/*`: A brand new router supporting `/regions/countries`, `/regions/states`, and `/regions/distribution-centers` for frontend dropdowns and region selectors.
- `/weather/festivals` and `/weather/climate-profiles`: Extended with `country_code` filtering to allow regionalized insights.

See `API_README.md` for full API endpoint documentation.

## Running Tests

All core validation suites, schema validations, and full-pipeline agent orchestrations have been validated against the expanded data footprint. You can run all tests to verify the pipeline behavior using the native commands:

```bash
python -m pytest tests/test_weather_festival_schema.py -v
python -m pytest tests/test_policy_agent.py -v
python tests/test_demand_forecast_agent.py
python tests/test_full_pipeline_integration.py
```
