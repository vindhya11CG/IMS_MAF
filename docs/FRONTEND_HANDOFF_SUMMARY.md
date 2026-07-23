# Frontend Handoff Summary

## Backend status

The backend has been verified and is ready for frontend integration.

### Live API docs
- Swagger UI: http://127.0.0.1:8000/docs#/
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

### Verified evidence
- Regression tests: `24 passed in 4.22s`
- Live OpenAPI route count: `54` endpoint paths
- Live smoke checks confirmed the following routes are responding:
  - `GET /api/v1/forecasting/health` → healthy
  - `GET /api/v1/dashboard/overview` → valid response
  - `GET /api/v1/regions/countries` → valid response

## Base integration details

- Base URL: `http://127.0.0.1:8000`
- API prefix: `/api/v1`

## Main route groups

### 1. Agent operations
- `POST /api/v1/agent/run-full`
- `GET /api/v1/agent/status`
- `GET /api/v1/agent/last-run`
- `GET /api/v1/agent/analysis/risks`
- `GET /api/v1/agent/analysis/replenishment`

### 2. Dashboard
- `GET /api/v1/dashboard/overview`
- `GET /api/v1/dashboard/summary`

### 3. Inventory
- `GET /api/v1/inventory/snapshots`
- `GET /api/v1/inventory/positions`
- `POST /api/v1/inventory/reorder`
- `POST /api/v1/inventory/risk`

### 4. Products
- `GET /api/v1/products/`
- `GET /api/v1/products/{product_id}`
- `GET /api/v1/products/categories`
- `GET /api/v1/products/categories/{category_id}`
- `GET /api/v1/products/seasonal-patterns`
- `GET /api/v1/products/seasonal-patterns/{season_id}`
- `GET /api/v1/products/velocity-classes`
- `GET /api/v1/products/velocity-classes/{velocity_class_id}`

### 5. Locations and regions
- `GET /api/v1/locations/`
- `GET /api/v1/locations/stores`
- `GET /api/v1/locations/{location_id}`
- `GET /api/v1/regions/countries`
- `GET /api/v1/regions/states`
- `GET /api/v1/regions/distribution-centers`

### 6. Suppliers
- `GET /api/v1/suppliers/`
- `GET /api/v1/suppliers/{supplier_id}`
- `GET /api/v1/suppliers/performance`
- `GET /api/v1/suppliers/pricing-tiers`
- `GET /api/v1/suppliers/risk-profile`

### 7. Purchase history
- `GET /api/v1/purchase-history/summary`
- `GET /api/v1/purchase-history/top-products`
- `GET /api/v1/purchase-history/product/{product_id}`

### 8. Risks
- `GET /api/v1/risks/`
- `GET /api/v1/risks/detected`

### 9. Orders
- `GET /api/v1/orders/`
- `GET /api/v1/orders/summary`

### 10. Simulation
- `GET /api/v1/simulation/features`
- `POST /api/v1/simulation/simulate`

### 11. Weather and festival context
- `GET /api/v1/weather/context`
- `GET /api/v1/weather/festivals`
- `GET /api/v1/weather/climate-profiles`

### 12. Forecasting
- `GET /api/v1/forecasting/health`
- `GET /api/v1/forecasting/model/info`
- `GET /api/v1/forecasting/model/metrics`
- `GET /api/v1/forecasting/features`
- `POST /api/v1/forecasting/predict`
- `POST /api/v1/forecasting/predict/batch`
- `POST /api/v1/forecasting/forecast/{product_id}`
- `POST /api/v1/forecasting/inventory/reorder`
- `POST /api/v1/forecasting/inventory/risk`
- `POST /api/v1/forecasting/simulate`

## Recommended frontend development order

1. Dashboard overview
2. Products catalog
3. Locations and stores
4. Suppliers
5. Forecasting health and predictions

## Handoff note

The frontend team can begin integration immediately against the running backend at `http://127.0.0.1:8000`.
The Swagger UI is the fastest way to inspect payloads and test requests interactively.
