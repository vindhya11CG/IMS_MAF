FastAPI API for Inventory Management System
=========================================

Run the IMS via a lightweight FastAPI endpoint for testing and UI integration.

Install dependencies (create and activate your virtual env first):

```powershell
pip install -r requirements.txt
```

Run the API server:

```powershell
uvicorn api.app:app --reload --port 8000
```

Endpoints:
- `GET /run-agent` — runs the `InventoryMonitoringAgent` and returns a concise JSON summary

---

# Multi-Region Backend API Documentation

The Inventory Management System exposes a suite of FastAPI endpoints designed to seamlessly support the new multi-region footprint (US, IN, SE). These endpoints are used by frontend teams to render geographic hierarchies, display enriched location context, and drive region-specific UI features.

## 1. Regions Router (`/api/v1/regions`)

Exposes core geographic grouping to populate frontend filters and dropdowns.

### `GET /api/v1/regions/countries`
Returns a list of all distinct countries found in the database.
- **Response Format**: `List[Dict[str, str]]`
- **Fields**: `country_code`, `country_name`

### `GET /api/v1/regions/states`
Returns all states/provinces. 
- **Query Params**: `country_code` (optional) - Filter by a specific country code (e.g., `US`, `IN`, `SE`).
- **Response Format**: `List[Dict]`

### `GET /api/v1/regions/distribution-centers`
Returns all distribution center locations globally or by country.
- **Query Params**: `country_code` (optional) - Filter by country code.

## 2. Locations Router (`/api/v1/locations`)

Handles queries for individual operating units (Stores and DCs).

### `GET /api/v1/locations/`
Retrieves all locations with derived country contextual fields.
- **Query Params**: 
  - `location_type` (optional): Filter by `STORE` or `DC`.
  - `country_code` (optional): Filter by country code.
- **Added Response Fields**: `state_name`, `state_code`, `country_code`, `country`.

### `GET /api/v1/locations/stores`
Retrieves rich store metadata (such as opening dates, active flags, and DC affiliations).
- **Query Params**: `country_code` (optional)
- **Added Response Fields**: `state_name`, `country_code`, `country`.

### `GET /api/v1/locations/{location_id}`
Retrieves a specific location by ID.

## 3. Weather & Context Router (`/api/v1/weather`)

Handles queries for localized weather, climate, and festival data that shape demand forecasting.

### `GET /api/v1/weather/context`
Retrieves localized weather conditions and calculated severity/demand multiplier variables.

### `GET /api/v1/weather/festivals`
Retrieves regional festival calendar entries that impact demand lift and supply constraints.
- **Query Params**:
  - `location_id` (optional)
  - `country_code` (optional): Filter specifically for Indian, Swedish, or US holidays.

### `GET /api/v1/weather/climate-profiles`
Retrieves static climate benchmarks and sensitivity indices for each location.
- **Query Params**:
  - `location_id` (optional)
  - `country_code` (optional)

---

Notes:
- Keep your `.env` configured for Azure OpenAI if you want the Azure analysis step.
- Do not commit `.env` to source control.
