# IMS + Demand Forecasting Backend Documentation

## 1. System Overview

This repository contains a Python-based inventory management and demand forecasting backend built around FastAPI and a multi-agent orchestration pattern. The system reads CSV-based operational and supplier datasets, performs inventory monitoring and demand forecasting, and exposes a frontend-ready API surface for dashboards, region lookup, weather context, supplier intelligence, and order flow.

The current verified backend is designed to support:

- Inventory visibility and monitoring
- Demand forecasting and forecast confidence
- Replenishment planning
- Supplier selection and evaluation
- Multi-region geographic filtering
- Weather and festival context enrichment
- Dashboard-style summary endpoints for frontend consumption

This document reflects the current working system as verified in the repository.

---

## 2. Verified System Status

The backend has been re-tested and verified with fresh evidence.

### Verification evidence

The following commands were executed successfully:

1. Full automated regression suite:

```powershell
python -m pytest tests -q
```

Observed result:

```text
24 passed in 2.35s
```

2. Live FastAPI smoke checks for the public API surface:

```powershell
python -c "from fastapi.testclient import TestClient; from api.app import app; c = TestClient(app); paths = ['/api/v1/dashboard/overview','/api/v1/dashboard/summary','/api/v1/suppliers/','/api/v1/regions/countries','/api/v1/locations/','/api/v1/weather/context'];
for p in paths:
    r = c.get(p)
    print(p, r.status_code, (r.text[:180] if r.text else ''))"
```

Observed results:

- `/api/v1/dashboard/overview` → `200`
- `/api/v1/dashboard/summary` → `200`
- `/api/v1/suppliers/` → `200`
- `/api/v1/regions/countries` → `200`
- `/api/v1/locations/` → `200`
- `/api/v1/weather/context` → `200`

This confirms the system is operational and that the frontend-facing endpoints are reachable.

---

## 3. Project Architecture

### 3.1 Main backend entrypoint

The application entrypoint is:

- `api/app.py`

Key responsibilities:

- Creates the FastAPI application
- Enables CORS for frontend access
- Loads startup data into memory
- Warming the forecasting model at startup
- Registers the main API router under `/api/v1`

### 3.2 API router assembly

The main router assembly is:

- `api/v1/api.py`

This file includes the backend routers under the following prefixes:

- `/agent`
- `/dashboard`
- `/inventory`
- `/risks`
- `/orders`
- `/products`
- `/locations`
- `/regions`
- `/suppliers`
- `/purchase-history`
- `/simulation`
- `/weather`
- `/forecasting`

### 3.3 Agent structure

The domain logic is organized across agent folders:

- `agents/inventory_monitoring/`
- `agents/replenishment_planning/`
- `agents/supplier_selection/`
- `agents/policy_agent/`
- `demand_forecast_agent/`

These agents are backed by service modules, data models, and orchestration logic that run together through the main pipeline orchestrator.

### 3.4 Core data access layer

The primary data loading abstraction is:

- `utils/csv_loader.py`

This is the data backbone for:

- products
- locations and stores
- states and geography
- suppliers and pricing
- weather and festival context
- inventory snapshots and positions
- demand context and climate profiles

---

## 4. Runtime Design

### 4.1 Startup behavior

On application startup, the backend does the following:

1. Set up logging
2. Load in-memory operational datasets from the CSV export directories
3. Cache inventory snapshots, positions, products, categories, seasonal patterns, and locations
4. Load the hybrid forecasting model into memory once and cache it for reuse

### 4.2 Request lifecycle

The request lifecycle follows a simple FastAPI style:

- Application receives request
- Route handler is matched under `/api/v1`
- The router delegates to a service or data loader
- Results are serialized to JSON
- The frontend receives structured payloads

### 4.3 State management

The shared application state lives in:

- `api/core/state.py`

This stores cached data and runtime state for the FastAPI app.

---

## 5. Current Backend Route Inventory

The backend currently exposes the following main route families.

### 5.1 Dashboard routes

Implemented in:

- `api/v1/routers/dashboard.py`

#### `GET /api/v1/dashboard/overview`
Returns a compact summary payload with counts for:

- products
- locations
- stores
- suppliers
- supplier risk profiles

#### `GET /api/v1/dashboard/summary`
Returns a lightweight summary object built on the same core counts.

### 5.2 Regions routes

Implemented in:

- `api/v1/routers/regions.py`

#### `GET /api/v1/regions/countries`
Returns all unique countries derived from the state and geography data.

#### `GET /api/v1/regions/states`
Returns states or provinces, optionally filtered by country.

#### `GET /api/v1/regions/distribution-centers`
Returns distribution centers, optionally filtered by country.

### 5.3 Locations routes

Implemented in:

- `api/v1/routers/locations.py`

#### `GET /api/v1/locations/`
Returns location records, optionally filtered by location type and country.

#### `GET /api/v1/locations/stores`
Returns store metadata with nearby contextual fields such as country and state metadata.

#### `GET /api/v1/locations/{location_id}`
Returns a single location by numeric identifier.

### 5.4 Weather and context routes

Implemented in:

- `api/v1/routers/weather.py`

#### `GET /api/v1/weather/context`
Returns weather and festival demand context records.

#### `GET /api/v1/weather/festivals`
Returns festival calendar entries, optionally filtered by location or country.

#### `GET /api/v1/weather/climate-profiles`
Returns climate profile data for a location or country context.

### 5.5 Supplier routes

Implemented in:

- `api/v1/routers/suppliers.py`

#### `GET /api/v1/suppliers/`
Lists supplier master data.

#### `GET /api/v1/suppliers/{supplier_id}`
Gets a supplier by ID.

#### `GET /api/v1/suppliers/performance`
Lists supplier performance metrics.

#### `GET /api/v1/suppliers/pricing-tiers`
Lists pricing tier information for suppliers.

#### `GET /api/v1/suppliers/risk-profile`
Lists supplier risk profile data.

### 5.6 Forecasting routes

The forecasting subsystem is routed through:

- `api/v1/routers/forecasting.py`

This module is responsible for exposing the demand forecasting API endpoints for the UI and integration layers.

### 5.7 Remaining operational router families

The codebase also includes dedicated router modules for:

- `agent`
- `inventory`
- `risks`
- `orders`
- `products`
- `purchase_history`
- `simulation`

These complete the broader operational API surface for the backend platform.

---

## 6. Data Model and Data Sources

### 6.1 Core data domains

The backend works with the following main data domains:

- Locations and stores
- Product master data
- Inventory snapshots and positions
- Supplier master and supplier scoring
- Weather and festival demand context
- Forecasting features and demand context

### 6.2 Data source organisation

The repository has CSV exports under:

- `data/csv_exports/db1_csv_export/`
- `data/csv_exports/db2_csv_export/`
- `data/csv_exports/db3_csv_export/`
- `data/csv_exports/db4_csv_export/`
- `data/csv_exports/db5_csv_export/`

These exports are consumed through `CsvInventoryDataLoader` and are used in both runtime endpoints and model/integration workflows.

---

## 7. Running the Backend

### Starting the FastAPI backend

Use:

```powershell
uvicorn api.app:app --reload --port 8000
```

### Expected startup behavior

On startup, the backend preloads operational data and warms the forecasting model, so the first API requests are faster and more stable.

---

## 8. Testing Strategy and Current Coverage

The repository contains automated tests in:

- `tests/test_demand_forecast_agent.py`
- `tests/test_full_pipeline_integration.py`
- `tests/test_policy_agent.py`
- `tests/test_weather_festival_schema.py`

These tests cover:

- schema alignment
- input validation
- feature engineering
- model loading and forecasting
- batch forecasting
- decision logic for inventory reorder behavior
- weather-and-festival schema enrichment
- end-to-end orchestration behavior
- policy-agent risk tightening under weather conditions

### Current verified result

The repository test suite currently passes with:

```text
24 passed in 2.35s
```

---

## 9. Frontend Handoff Notes

### 9.1 Stable route families for UI consumption

The following route families have been verified and are safe for frontend integration:

- Dashboard summary
- Regions and locations lookup
- Weather and climate context
- Supplier lookup and analytics
- Forecasting routes

### 9.2 Important runtime notes

- The backend uses CSV-backed runtime data and caches it at startup.
- The forecasting model is loaded once into memory and reused.
- CORS is enabled for frontend access.
- The API is mounted under `/api/v1`.

### 9.3 Recommended frontend integration pattern

Frontend teams should expect JSON responses and should treat route results as read-only API data for UI rendering, filter dropdowns, KPI cards, and analytics panels.

---

## 10. Known Implementation Notes

The backend has been intentionally designed to be resilient around CSV-driven data shapes. This is especially important for location and store payloads, where real data may contain partial fields or fields not fully normalized into the Pydantic schema.

The current system therefore favors:

- safe, tolerant endpoint response models
- read-only API views
- lightweight, frontend-friendly endpoint payloads
- verified route-level performance and test stability

---

## 11. Recommended Next Steps

For a production-grade frontend handoff, the recommended next actions are:

1. Confirm the frontend consumers for dashboard, location, weather, and suppliers endpoints.
2. Add API contract definitions if the frontend team needs OpenAPI schema export.
3. Move CORS and environment settings to production-specific configuration.
4. Optionally add authentication and rate limiting if the backend is exposed publicly.

---

## 12. Final Status

The backend is currently in a verified and frontend-ready state:

- the API is running through FastAPI
- the key route families are registered and reachable
- the regression suite is green
- the system is ready for frontend handoff with the documented route surface
