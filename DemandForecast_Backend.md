# Demand Forecasting & Inventory Management System

A multi-agent inventory management backend: four independently-built agents
(Inventory Monitoring, Demand Forecast, Replenishment Planning, Supplier
Selection) wired together by an orchestration layer, with an optional Azure
OpenAI layer for narrative analysis on top of each agent's structured output.

## Architecture

```
InventoryMonitoringAgent.execute()
       |  positions + snapshots -> RiskAssessment list (heuristic forecast)
       v
PipelineOrchestrator: for each risk_detected=True row
       |  builds a payload -> DemandForecastAgent.execute() -> real ML forecast
       |  dataclasses.replace(assessment, forecasted_demand=..., ...)
       v
ReplenishmentPlanningAgent.execute(enhanced_assessments)
       |  EOQ calculation + supplier matching -> ReplenishmentOrder list
       v
SupplierSelectionAgent.execute(orders)
       |  policy evaluation + scoring -> SupplierSelectionResult list
       v
Final result: monitoring + replenishment + supplier_selection
```

The orchestrator (`orchestration/pipeline_orchestrator.py`) never modifies the
three pre-existing agents' internal logic - it only calls their public
`.execute()` methods and translates data between them.

## Prerequisites

- Python 3.11+
- `make` (Linux/macOS native; on Windows use WSL, Git Bash, or `choco install make`)
- (Optional) an Azure OpenAI resource, if you want the narrative `azure_analysis` fields

## Quick Start

```bash
make venv
source venv/bin/activate        # venv\Scripts\activate on Windows
make install
make data                       # generate the synthetic training dataset
make train                      # feature-engineer, train, save the hybrid model
make test                       # run both offline test suites
make run                        # run the full 5-agent pipeline end-to-end
```

Run `make help` for the full list of targets.

## Configuration

Copy `.env.example` to `.env` and fill in real values:

```bash
cp .env.example .env
```

`.env` is gitignored - never commit real credentials. The system runs fully
offline without Azure configured; `AZURE_OPENAI_*` values only enable the
narrative `azure_analysis` fields on top of each agent's structured output.

## Testing

**Offline (no Azure needed):**
```bash
make test-forecast    # tests/test_demand_forecast_agent.py
make test-pipeline    # tests/test_full_pipeline_integration.py (verifies the no-Azure guarantee)
```

**With Azure OpenAI configured in `.env`:**
```bash
make smoke-azure            # verifies the connection directly (bypasses silent fallbacks)
make test-forecast          # now exercises the live endpoint automatically
make smoke-azure-pipeline   # runs the full pipeline once with Azure wired into all 3 agents
```

`smoke-azure-pipeline` and the smoke-test scripts are deliberately separate
from `make run` - they cap `MAX_ML_FORECAST_CALLS` low for speed during a
connectivity check. Use `make run` (or `python orchestration/pipeline_orchestrator.py`
directly) for a real, uncapped run.

## Project Layout

| Path | Purpose |
|---|---|
| `agents/inventory_monitoring/` | Load snapshots/positions, calculate stock, detect risk |
| `agents/replenishment_planning/` | EOQ-based purchase order generation |
| `agents/supplier_selection/` | Policy-based supplier evaluation and selection |
| `demand_forecast_agent/` | Hybrid SARIMAX + XGBoost forecasting service |
| `orchestration/pipeline_orchestrator.py` | Wires all four agents together |
| `training_models/` | Data prep, model training, the trained artifacts |
| `api/app.py` | FastAPI endpoint (`/run-agent`) for Inventory Monitoring |
| `config/azure_config.py` | Azure OpenAI client, shared across all agents |
| `tests/` | Offline test suites + manual Azure smoke-test scripts |
| `data/csv_exports/db1-db5_csv_export/` | Reference data (locations, products, suppliers, inventory, snapshots) |

## Recent Fixes (finalization pass, July 2026)

Found by inspecting a full pipeline run's output JSON:

- **Replenishment and supplier-selection orders showed `lead_time_days=0` and
  `min_order_qty=0` on every single order.** Both services were reading these
  fields off `suppliers.csv`, which has neither column - the real values live
  on `supplier_category_mapping.csv` (`lead_time_days`, `moq_units`), keyed by
  `(supplier_id, category_id)`. Fixed in `SupplierMatchingService` and
  `SupplierSelectionAgent._get_supplier_lead_time`.
- **A handful of assessments showed negative `current_stock`** (physically
  impossible for on-hand inventory). Added the same non-negative guard that
  snapshot validation already had, to the position-fallback and snapshot
  accounting paths in `InventoryCalculationService`, with a warning log.
- **The demand-forecast payload built by the orchestrator only populated 3 of
  the ~10 non-trivial features the model was trained on**, leaving
  `lead_time_days`, `season_multiplier`, and `annual_units_max` (→
  `velocity_score`) to silently zero-fill at inference - values the model
  never saw in training. Enriched the payload from `supplier_category_mapping.csv`,
  `velocity_classes.csv`, and `seasonal_patterns.csv` where available.

## Known Limitations

- **`inventory_daily_snapshots.csv` (DB5) and `inventory_positions.csv` (DB3)
  currently use non-overlapping SKU/location ID spaces** in the synthetic
  dataset - 0 of ~975 snapshot keys match any of the ~166k real positions.
  This means the *heuristic* demand estimate inside Inventory Monitoring is
  effectively always 0 for real positions (it falls back to `sales=0` for
  position-only rows). The trained ML model, invoked by the orchestrator for
  every risk-flagged row, is the real source of truth for `forecasted_demand`
  - not the heuristic. If/when snapshots and positions are regenerated from a
  shared ID space, the heuristic becomes meaningful again too.
- **Six model features have no live data source today**: `demand_std_dev`,
  `total_orders_last_month`, `turnover_ratio`, `order_fulfillment_rate`,
  `holding_cost_per_unit_day`, and `handling_cost_per_unit` exist only in the
  training-time synthetic CSV (`synthetic_inventory_db_native.csv`) and have
  no corresponding table anywhere in DB1-DB5. They will reindex to 0 at live
  inference until either the model is retrained on a feature set restricted
  to what's actually reconstructable from DB1-DB5, or those values get a real
  source table.
- **Three legacy pre-consolidation files remain in `demand_forecast_agent/services/`**
  (`forecast_service.py`, `model_loader_service.py`, `confidence_service.py`,
  `logging_service.py`, `explanation_service.py`) - none are imported by
  `__init__.py` anymore. Safe to delete; kept for now to avoid an unreviewed
  deletion in this pass.
- `MAX_ML_FORECAST_CALLS` (default 200) caps ML-enhanced rows per run; raise
  it for a full nightly batch on a larger dataset.

---

## Phase 6: Weather & Festival Demand Integration (July 2026)

The system has been fully extended with weather, festival, seasonal, and regional demand context signals across all 5 pipeline agents, data loaders, feature engineering, model inference, and backend FastAPI endpoints.

### Key Additions & Schema Architecture

#### 1. Database Schema (`data/csv_exports/db6_csv_export/`)
Three synthetic database tables provide weather, festival, and regional demand signals:
- **`demand_context_fact.csv`**: Daily weather observations, severity indices, risk scores, and festival flags per (SKU, location).
- **`festival_calendar.csv`**: Reference table of national & local festivals, dates, and expected demand lift.
- **`location_climate_profile.csv`**: Climate zones, weather sensitivity scores, and regional demand indices per location.

#### 2. Core Data Models (`agents/inventory_monitoring/models/inventory_models.py`)
- **`WeatherFestivalContext`**: Lightweight context carrier object containing:
  - Multipliers & Risk Scores: `weather_demand_multiplier`, `weather_severity_index`, `supply_disruption_risk`, `climate_anomaly_score`, `regional_demand_index`.
  - Condition Flags: `heatwave_flag`, `coldwave_flag`, `monsoon_flag`, `heavy_rain_flag`, `snowfall_flag`, `extreme_weather_flag`.
  - Festival Flags: `is_festival_day`, `festival_proximity_score`, `is_shopping_season`.
  - Helper Methods: `is_high_risk()`, `effective_demand_multiplier()` (capped at 2.5×), `describe_risks()`.
- **`RiskAssessment`**: Extended with `weather_context: Optional[WeatherFestivalContext] = None` (fully backward-compatible).

#### 3. Agent & Pipeline Updates
- **`CsvInventoryDataLoader`**: Added `load_demand_context_fact()`, `load_festival_calendar()`, `load_location_climate_profile()`, and `build_weather_context_map()`.
- **`InventoryRiskMonitoringService`**: Forecasted demand scales by `effective_demand_multiplier()`. Weather & festival risk reasons are appended to `risk_reasons`.
- **`OrderCalculationService`**: Economic Order Quantity (EOQ) uses weather-adjusted demand. Order priority elevates to `URGENT` under extreme weather or high supply disruption.
- **`PolicyEvaluationService`**: Tightens minimum supplier reliability threshold by `0.05` when `weather_supply_risk > 0.6`.
- **`PipelineOrchestrator`**: Injects 8 weather context fields into `DemandForecastAgent` payloads and tracks `weather_context_loaded`.

#### 4. Extended MODEL_FEATURES (33 features total)
`FeatureEngineeringService.MODEL_FEATURES` includes 8 weather/festival features:
- `weather_demand_multiplier`
- `weather_severity_index`
- `is_festival_day_int`
- `festival_proximity_score`
- `is_shopping_season_int`
- `supply_disruption_risk`
- `climate_anomaly_score`
- `regional_demand_index`

*Backward compatibility:* `to_model_matrix()` reindexes missing columns to `0` at inference time.

#### 5. Backend FastAPI Endpoints (`api/v1/routers/weather.py`)
Registered 3 new endpoints under `/api/v1/weather`:
- **`GET /api/v1/weather/context`**: Query weather & festival demand facts (supports filtering by `product_id` & `location_id`).
- **`GET /api/v1/weather/festivals`**: Query festival calendar entries (supports filtering by `location_id`).
- **`GET /api/v1/weather/climate-profiles`**: Query location climate profiles (supports filtering by `location_id`).
- **Updated `POST /api/v1/forecasting/predict` & `/predict/batch`**: Accepts optional weather and festival context fields in request payloads.

#### 6. Test Suite & Verification
- `pytest tests/test_weather_festival_schema.py tests/test_policy_agent.py`: **24/24 passed**.
- `python tests/test_demand_forecast_agent.py`: **60/60 passed**.
- `python tests/test_full_pipeline_integration.py`: **166,228 checks passed, 0 failed**.

---

## Makefile Target Reference

| Target | Description |
|---|---|
| `make venv` | Create Python virtual environment (`.venv`) |
| `make install` | Install all dependencies into `.venv` |
| `make schema-init` | Initialize db6 CSV exports |
| `make schema-validate` | Validate all CSV header counts |
| `make data` | Generate synthetic training CSV |
| `make prepare` | Clean data & engineer features |
| `make train` | Train Hybrid SARIMAX + XGBoost model |
| `make test` | Run all unit & integration test suites |
| `make test-schema` | Run weather schema tests |
| `make test-policy` | Run policy evaluation agent tests |
| `make test-forecast` | Run demand forecast agent tests |
| `make test-pipeline` | Run 5-agent pipeline integration tests |
| `make lint` | Run flake8 style checks |
| `make format` | Auto-format with black & isort |
| `make run` | Execute full pipeline (Azure OFF) |
| `make serve` | Start FastAPI development server (`uvicorn`) |
| `make clean` | Clean build & test caches |
| `make distclean` | Full clean including `.venv` and dataset |

