# IMS + Demand Forecasting Project Documentation

## 1. Executive Summary

This repository implements a multi-agent inventory management and demand forecasting system. The runtime path is:

1. `main.py` creates an `AgentOrchestrator`
2. `AgentOrchestrator` runs the inventory-monitoring agent, replenishment agent, supplier-selection agent, and policy re-check
3. The FastAPI backend in `api/app.py` exposes inventory, forecast, weather/festival, simulation, and analytics endpoints
4. The demand forecast engine in `demand_forecast_agent/` uses a hybrid SARIMAX + XGBoost workflow with feature engineering and caching

Important note: the project is CSV-export driven. The system uses data files under `data/csv_exports/` and synthetic enrichment files such as `synthetic_inventory_weather_region_v2_festival_demand.csv`; it does not contain a dedicated live relational DB layer in this repo.

---

## 2. Data / DB Schema Reference

### Source schema groups

- DB1: location / network reference data
  - Files: `data/csv_exports/db1_csv_export/*`
  - Typical business objects: location master, state, country, store/DC mapping

- DB2: product master data
  - Files: `data/csv_exports/db2_csv_export/*`
  - Typical business objects: SKU, category, seasonal profile, velocity class

- DB3: inventory core positions and in-transit inventory
  - Files: `data/csv_exports/db3_csv_export/*`
  - Typical business objects: `inventory_positions.csv`, `in_transit_inventory.csv`

- DB4: supplier master and pricing data
  - Files: `data/csv_exports/db4_csv_export/*`
  - Typical business objects: suppliers, supplier category mapping, pricing tiers, performance

- DB5: operational snapshots and event history
  - Files: `data/csv_exports/db5_csv_export/*`
  - Typical business objects: `inventory_daily_snapshots.csv`, `inventory_events.csv`

- DB6 / weather-festival extension
  - Files: `data/csv_exports/db6_csv_export/*`
  - Typical business objects: `demand_context_fact.csv`, `festival_calendar.csv`, `location_climate_profile.csv`

### Enrichment schema used by the forecasting and risk engine

- `synthetic_inventory_weather_region_v2_festival_demand.csv`
- Adds weather and festival context columns such as:
  - `temperature_c`, `humidity_pct`, `rainfall_mm`
  - `weather_severity_index`, `weather_demand_multiplier`
  - `is_festival_day`, `festival_proximity_score`, `is_shopping_season`

These fields are meant to enrich the inventory and demand model without changing the original inventory schema.

---

## 3. File Manifest

### 3.1 Entry Point and orchestration

| File | What it does | Data schema used | Agents / services involved | Main functions |
|---|---|---|---|---|
| `main.py` | Runs the complete workflow from the command line and prints phase summaries. | All CSV export sources via loader classes. | `AgentOrchestrator`, `AzureOpenAIClient` | `main()` |
| `agent_orchestrator.py` | Coordinates the full 5-phase pipeline. | DB3/DB4/DB5 + weather context if present. | `InventoryMonitoringAgent`, `ReplenishmentPlanningAgent`, `SupplierSelectionAgent`, `PolicyAgent` | `execute()`, `_build_workflow_summary()` |
| `api/app.py` | FastAPI application bootstrap and startup preload. | Cached raw data from `CsvInventoryDataLoader` and model warm-up. | FastAPI app + demand-forecast model loader | `startup_event()` |
| `api/v1/api.py` | Route registration / mount points for all API feature groups. | N/A | All routers | `api_router.include_router(...)` |

### 3.2 Inventory monitoring agent stack

| File | What it does | Data schema used | Agents / services involved | Main functions |
|---|---|---|---|---|
| `agents/inventory_monitoring/agent.py` | Phase 1-3 runtime controller: snapshots -> calculations -> risk. | DB3, DB5, DB6 weather/festival context | `EventSnapshotService`, `InventoryCalculationService`, `InventoryRiskMonitoringService` | `execute()`, `_build_openai_prompt()`, `_generate_local_summary()` |
| `agents/inventory_monitoring/services/event_snapshot_service.py` | Loads, validates, and normalizes snapshot data. | DB5 snapshot schema | Event snapshot validation | `execute()` |
| `agents/inventory_monitoring/services/calculation_service.py` | Converts positions + snapshots into current stock calculations. | DB3 + DB5 | inventory math | `execute()` |
| `agents/inventory_monitoring/services/risk_monitoring_service.py` | Computes risk reasons and forecast-adjusted risk. | DB3 + DB5 + weather/festival context | risk scoring logic | `execute()`, `estimate_forecasted_demand()` |
| `agents/inventory_monitoring/models/inventory_models.py` | Dataclasses for inventory positions, snapshots, risk assessments, and weather festival context. | Internal domain schema | Pydantic-like dataclasses | `InventoryPosition`, `InventorySnapshot`, `RiskAssessment`, `WeatherFestivalContext` |

### 3.3 Replenishment planning agent stack

| File | What it does | Data schema used | Agents / services involved | Main functions |
|---|---|---|---|---|
| `agents/replenishment_planning/agent.py` | Converts risk assessments into replenishment orders. | Risk outputs from Phase 3, supplier/price lookups | `SupplierMatchingService`, `OrderCalculationService` | `execute()`, `_generate_summary()`, `_build_openai_prompt()` |
| `agents/replenishment_planning/services/supplier_matching_service.py` | Matches risky SKUs to candidate suppliers. | DB4 supplier mapping + pricing/lead-time data | supplier selection pre-step | `execute()` |
| `agents/replenishment_planning/services/order_calculation_service.py` | Calculates order quantity, lead time, cost, urgency. | DB3 + DB4 + risk assessment input | EOQ and order planning | `execute()` |
| `agents/replenishment_planning/models/*` | Replenishment order and summary models. | Internal replenishment schema | domain models | `ReplenishmentOrder`, `ReplenishmentPlanSummary`, `SupplierInfo` |

### 3.4 Supplier-selection and policy stack

| File | What it does | Data schema used | Agents / services involved | Main functions |
|---|---|---|---|---|
| `agents/supplier_selection/agent.py` | Evaluates alternative suppliers and applies policy rules. | DB4 supplier master and category mapping | `PolicyEvaluationService`, `SupplierEvaluationService` | `execute()`, `_evaluate_and_select_suppliers()`, `_get_supplier_unit_cost()`, `_get_supplier_lead_time()` |
| `agents/supplier_selection/services/policy_evaluation_service.py` | Applies procurement policy rules to supplier evaluations. | supplier evaluation output + policy config | policy logic | `execute()`, `get_policy()` |
| `agents/supplier_selection/services/supplier_evaluation_service.py` | Scores suppliers across cost, lead time, reliability, and policy fit. | DB4 supplier pricing and performance | supplier scoring | `execute()` |
| `agents/policy_agent/agent.py` | Lightweight re-validation of supplier evaluations using the same policy service. | Supplier evaluation schema | `PolicyEvaluationService` | `execute()` |

### 3.5 Demand forecasting stack

| File | What it does | Data schema used | Agents / services involved | Main functions |
|---|---|---|---|---|
| `demand_forecast_agent/agent.py` | Forecast agent entrypoint for model invocation. | engineered feature vectors from inventory and product data | forecast services | `execute()` |
| `demand_forecast_agent/services/core_forecasting_service.py` | Main hybrid forecasting engine and inference orchestrator. | model artifact + feature-engineered input | SARIMAX/XGBoost ensemble | `ForecastService.execute()` |
| `demand_forecast_agent/services/feature_engineering_service.py` | Converts raw inventory / product inputs to model matrix. | DB2/DB3/DB5/DB6 enriched features | feature preparation | `execute()`, `to_model_matrix()` |
| `demand_forecast_agent/services/decision_services.py` | Reorder decision and risk/stock decision helpers for API inventory routes. | forecast output + stock data | decision logic | `InventoryDecisionService.execute()`, `ReorderService.execute()` |
| `training_models/model_training.py` | Trains the hybrid model and saves artifacts. | synthetic train dataset | training workflow | `train_model()` |
| `training_models/data_preparation.py` | Prepares clean training datasets and feature engineering context. | synthetic inventory CSVs | data prep | data transformation functions |

### 3.6 Data loader and utilities

| File | What it does | Data schema used | Main functions |
|---|---|---|---|
| `utils/csv_loader.py` | Shared loader for inventory, product, supplier, pricing, seasonal, and weather/festival reference tables. | DB1-DB6 reference data | `load_inventory_positions()`, `load_inventory_daily_snapshots()`, `load_products()`, `load_locations()`, `load_demand_context_fact()`, `build_weather_context_map()` |
| `utils/logging_setup.py` | Central logging configuration. | N/A | `setup_logging()` |
| `config/azure_config.py` | Azure OpenAI configuration builder and client. | Azure env config | `AzureOpenAIConfig.from_env()`, `AzureOpenAIClient` |

---

## 4. System Features and File Coverage

### Feature 1: Full multi-agent inventory workflow
- Description: monitors inventory positions, snapshots, and risk conditions; then plans replenishment and supplier selection.
- Files involved:
  - `main.py`
  - `agent_orchestrator.py`
  - `agents/inventory_monitoring/agent.py`
  - `agents/replenishment_planning/agent.py`
  - `agents/supplier_selection/agent.py`
  - `agents/policy_agent/agent.py`

### Feature 2: Inventory risk detection
- Description: identifies at-risk SKUs based on current stock, reorder point, safety stock, projected demand, and weather/festival modifiers.
- Files involved:
  - `agents/inventory_monitoring/services/risk_monitoring_service.py`
  - `agents/inventory_monitoring/models/inventory_models.py`
  - `api/v1/routers/inventory.py` (`/risk`)
  - `api/v1/routers/forecasting.py` (`/risk`)

### Feature 3: Demand forecasting
- Description: hybrid SARIMAX + XGBoost demand predictions with model metadata and metrics exposure.
- Files involved:
  - `demand_forecast_agent/services/core_forecasting_service.py`
  - `demand_forecast_agent/services/feature_engineering_service.py`
  - `api/v1/routers/forecasting.py`
  - `api/v1/schemas/forecasting.py`

### Feature 4: Reorder recommendation and replenishment planning
- Description: generates recommended order quantities and urgency from forecasted demand and inventory position.
- Files involved:
  - `agents/replenishment_planning/services/order_calculation_service.py`
  - `api/v1/routers/inventory.py` (`/reorder`)
  - `api/v1/routers/forecasting.py` (`/reorder`)

### Feature 5: Supplier evaluation and policy enforcement
- Description: evaluates each candidate supplier, compares against policy thresholds, and records exceptions.
- Files involved:
  - `agents/supplier_selection/agent.py`
  - `agents/supplier_selection/services/policy_evaluation_service.py`
  - `agents/supplier_selection/services/supplier_evaluation_service.py`

### Feature 6: Weather and festival demand context integration
- Description: enriches the demand/risk model with weather severity, climate profile, and festival signals.
- Files involved:
  - `WEATHER_FESTIVAL_SCHEMA.md`
  - `utils/csv_loader.py`
  - `agents/inventory_monitoring/agent.py`
  - `agents/inventory_monitoring/services/risk_monitoring_service.py`
  - `api/v1/routers/weather.py`

### Feature 7: Purchase history analytics
- Description: provides purchase-history summaries by window, category, and product.
- Files involved:
  - `api/v1/routers/purchase_history.py`
  - `api/v1/schemas/purchase_history.py`
  - `api/v1/services/purchase_history_service.py`

### Feature 8: What-if simulation
- Description: allows scenario-style simulation of demand and reorder behavior using a request payload.
- Files involved:
  - `api/v1/routers/simulation.py`
  - `api/v1/schemas/simulation.py`

### Feature 9: Reference-data browsing
- Description: gives product, location, category, seasonal pattern, and velocity-class lookup endpoints.
- Files involved:
  - `api/v1/routers/products.py`
  - `api/v1/routers/locations.py`
  - `api/v1/schemas/products.py`

---

## 5. Backend Endpoint Map

### 5.1 Agent control endpoints

| Endpoint | Purpose | Schema in use | Main code path |
|---|---|---|---|
| `POST /api/v1/agent/run-full` | Starts the full agent pipeline in the background. | N/A | `api/v1/routers/agent.py -> run_agent_full()` |
| `GET /api/v1/agent/status` | Returns the current pipeline status. | N/A | `get_agent_status()` |
| `GET /api/v1/agent/last-run` | Returns last execution timestamp and workflow summary. | N/A | `get_last_run()` |
| `GET /api/v1/agent/analysis/risks` | Returns Azure narrative analysis for risk results. | `state.results.phase_1_3_results` | `get_risk_analysis()` |
| `GET /api/v1/agent/analysis/replenishment` | Returns Azure analysis for replenishment results. | `state.results.phase_4_results` | `get_replenishment_analysis()` |

### 5.2 Inventory endpoints

| Endpoint | Purpose | Schema in use | Main code path |
|---|---|---|---|
| `GET /api/v1/inventory/snapshots` | Returns snapshot load data used by the monitoring agent. | Raw snapshot payloads from `state.raw_data` | `get_snapshots()` |
| `GET /api/v1/inventory/positions` | Returns baseline inventory positions. | Raw position payloads from `state.raw_data` | `get_positions()` |
| `POST /api/v1/inventory/reorder` | Generates reorder recommendations for inventory items. | `InventoryReorderRequest`, `InventoryReorderResponse` from `api/v1/schemas/inventory.py` | `reorder_recommendations()` |
| `POST /api/v1/inventory/risk` | Scores inventory positions and returns risk reasons. | `InventoryRiskRequest`, `InventoryRiskResponse` | `inventory_risk_scoring()` |

### 5.3 Forecasting endpoints

The forecasting router is mainly around `/api/v1/forecasting` and uses the Pydantic schemas in `api/v1/schemas/forecasting.py`.

| Endpoint | Purpose | Schema in use | Main code path |
|---|---|---|---|
| `GET /api/v1/forecasting/health` | Returns API load health and model readiness. | `HealthData`, `ApiResponse` | `health_check()` |
| `GET /api/v1/forecasting/model/info` | Returns model metadata and artifact paths. | `ModelInfoData` | `get_model_info()` |
| `GET /api/v1/forecasting/model/metrics` | Returns train / validation / test metrics. | `ModelMetricsData` | `get_model_metrics()` |
| `GET /api/v1/forecasting/features` | Returns feature definitions used by the model. | `FeatureListData` | `get_feature_list()` |
| `POST /api/v1/forecasting/predict` | Gives a single forecast for one product/location row. | `PredictRequest`, `PredictData` | `predict()` |
| `POST /api/v1/forecasting/predict/batch` | Performs vectorized batch prediction. | `BatchPredictRequest`, `BatchPredictData` | `predict_batch()` |
| `POST /api/v1/forecasting/forecast` | Produces an N-day rolling forecast. | `ForecastRequest`, `ForecastData` | `forecast()` |
| `POST /api/v1/forecasting/reorder` | Reorder recommendation using forecast and inventory state. | `ReorderRequest`, `ReorderData` | `reorder()` |
| `POST /api/v1/forecasting/risk` | Forecast-based inventory risk scoring. | `RiskRequest`, `RiskData` | `risk()` |
| `POST /api/v1/forecasting/simulate` | What-if simulation. | `SimulateRequest`, `SimulateData` | `simulate()` |

### 5.4 Weather and festival endpoints

| Endpoint | Purpose | Schema in use | Main code path |
|---|---|---|---|
| `GET /api/v1/weather/context` | Returns weather / festival demand context records. | Raw context records from `load_demand_context_fact()` | `get_weather_context()` |
| `GET /api/v1/weather/festivals` | Returns festival calendar entries. | Raw festival calendar records | `get_festivals()` |
| `GET /api/v1/weather/climate-profiles` | Returns location climate profile records. | Raw climate profile records | `get_climate_profiles()` |

### 5.5 Reference-data endpoints

| Endpoint | Purpose |
|---|---|
| `/api/v1/products/*` | Product, category, seasonal pattern, velocity class, and product-by-ID lookups |
| `/api/v1/locations/*` | Location list and single-location details |
| `/api/v1/orders/*` | Order summary and aggregated order readout |
| `/api/v1/risks/*` | Risk list and risk-detected summaries |
| `/api/v1/purchase-history/*` | Historical purchase analytics |
| `/api/v1/simulation/*` | Feature list and scenario simulation |

---

## 6. Agent-to-Feature Relationship

- `InventoryMonitoringAgent` owns the monitoring / risk-calculation workflow.
- `ReplenishmentPlanningAgent` owns demand-to-order conversion.
- `SupplierSelectionAgent` owns final supplier score and policy compliance.
- `PolicyAgent` is a cross-check / compliance layer that reuses the supplier policy engine.
- `DemandForecastAgent` is the machine-learning forecasting engine used by inventory risk and reorder features.

---

## 7. Architectural Notes

- The system is built around a service-oriented design with domain models and CSV-backed loaders.
- Most pipeline logic is synchronous and deterministic, while Azure OpenAI integration is optional and narrative-only.
- The API uses FastAPI and Pydantic schemas for request/response validation.
- The majority of the project’s runtime state is housed in `api/core/state.py` and preloaded in `api/app.py` on startup.

---

## 8. Recommended Reading Order

1. `main.py`
2. `agent_orchestrator.py`
3. `agents/inventory_monitoring/agent.py`
4. `agents/replenishment_planning/agent.py`
5. `agents/supplier_selection/agent.py`
6. `api/app.py`
7. `api/v1/routers/forecasting.py`
8. `WEATHER_FESTIVAL_SCHEMA.md`
9. `DemandForecast_Backend.md`

---

## 9. Practical Interpretation

The project is not a classic relational DB application. Instead, it is a Python orchestration + forecasting + API layer built over CSV export datasets. The dominant data contracts are:

- inventory snapshots and positions
- product / category / seasonal metadata
- supplier pricing and category mappings
- weather/festival context enrichment

So the “database schema” in this repo is best understood as a logical schema implied by the CSV exports and join keys, not as a schema implemented by a SQL database.
