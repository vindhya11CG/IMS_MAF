# Weather & Festival Integration — Developer Guide

## Overview

This document describes the Phase 6 weather and festival demand integration that
was added to the IMS-MAF pipeline. It covers schema changes, agent/service updates,
forecasting enhancements, migration steps, Makefile usage, and the testing guide.

---

## 1. Schema Changes

### New DB6 CSV Export Tables

Three new CSV tables under `data/csv_exports/db6_csv_export/` provide weather,
festival, and regional demand context for offline development and testing. They
serve as synthetic equivalents of the full 469 MB LFS dataset.

| Table | Purpose | Key Columns |
|---|---|---|
| `demand_context_fact.csv` | Per-SKU/location weather & festival signals | `weather_demand_multiplier`, `is_festival_day`, `supply_disruption_risk`, `regional_demand_index` |
| `festival_calendar.csv` | Reference: known festivals by location & date | `festival_name`, `demand_lift_pct`, `supply_risk_score`, `festival_type` |
| `location_climate_profile.csv` | Climate characteristics per location | `climate_zone`, `weather_sensitivity_score`, `regional_demand_index` |

### Extended Data Models (`inventory_models.py`)

**`WeatherFestivalContext`** — new lightweight dataclass carrying the weather/festival
signals needed at each pipeline stage:

```python
@dataclass
class WeatherFestivalContext:
    weather_demand_multiplier: float = 1.0      # neutral = 1.0
    weather_severity_index: float = 0.0         # 0–1 scale
    supply_disruption_risk: float = 0.0         # 0–1 scale
    is_festival_day: bool = False
    festival_proximity_score: float = 0.0       # 0–1 scale
    is_shopping_season: bool = False
    regional_demand_index: float = 1.0          # neutral = 1.0
    # … + weather flags, temperature, rainfall, etc.

    def is_high_risk(self) -> bool: ...
    def effective_demand_multiplier(self) -> float: ...  # capped at 2.5×
    def describe_risks(self) -> list[str]: ...
```

**`RiskAssessment`** — extended with an optional field (backward-compatible):

```python
@dataclass
class RiskAssessment:
    # … existing fields unchanged …
    weather_context: Optional[WeatherFestivalContext] = None  # NEW
```

---

## 2. Agent & Service Updates

### CSV Loader (`utils/csv_loader.py`)

Three new loaders + one aggregation helper:

```python
loader = CsvInventoryDataLoader()
loader.load_demand_context_fact()       # db6 demand context rows
loader.load_festival_calendar()          # festival calendar reference
loader.load_location_climate_profile()  # location climate profiles
loader.build_weather_context_map()      # dict: (sku_id, loc_id) → WeatherFestivalContext
```

`build_weather_context_map()` auto-selects the best data source:

1. **LFS file** (`synthetic_inventory_weather_region_v2_festival_demand.csv` at repo root) if present.
2. **db6 samples** (`demand_context_fact.csv`) as offline fallback.
3. **Empty dict** (graceful degradation) if neither is readable.

### Inventory Monitoring Agent (`inventory_monitoring/agent.py`)

- Calls `loader.build_weather_context_map()` at startup.
- Passes `weather_context_map` to `InventoryRiskMonitoringService.execute()`.
- Returns `weather_context_loaded` count in result dict.
- Enriches Azure OpenAI prompt with weather/festival context for top-risk items.

### Risk Monitoring Service (`risk_monitoring_service.py`)

- `execute()` / `assess_risk()` gain optional `weather_context_map` parameter.
- When context is available, forecasted demand is scaled:
  `effective_demand = ceil(base_demand × context.effective_demand_multiplier())`
- Weather/festival risk reasons appended to `RiskAssessment.risk_reasons`.
- `WeatherFestivalContext` attached to `RiskAssessment.weather_context`.

### Order Calculation Service (`order_calculation_service.py`)

- EOQ uses weather-adjusted annual demand.
- Priority elevated to `URGENT` when `extreme_weather_flag=True` or `supply_disruption_risk > 0.7`.
- `reasoning` string includes weather/festival multiplier details.

### Policy Evaluation Service (`policy_evaluation_service.py`)

- `evaluate_supplier()` gains `weather_supply_risk: float = 0.0` parameter.
- When `weather_supply_risk > 0.6`, effective reliability threshold rises by 0.05.
- Fully backward-compatible when parameter is not supplied.

### Pipeline Orchestrator (`pipeline_orchestrator.py`)

- `_build_forecast_payload()` injects 8 weather context fields from `assessment.weather_context`.
- `run()` result dict includes `weather_context_loaded` count.

---

## 3. Forecasting Enhancements

### New MODEL_FEATURES (8 added)

```python
FeatureEngineeringService.MODEL_FEATURES = [
    # … original 25 features unchanged …

    # Phase 6: Weather & Festival features
    "weather_demand_multiplier",   # 1.0 = no effect, >1 = demand boost
    "weather_severity_index",      # 0–1; severe = logistics/supply risk
    "is_festival_day_int",         # 0/1 from is_festival_day boolean
    "festival_proximity_score",    # 0–1; proximity to next/current festival
    "is_shopping_season_int",      # 0/1 from is_shopping_season boolean
    "supply_disruption_risk",      # 0–1; weather-driven supply risk
    "climate_anomaly_score",       # 0–1; deviation from climate normal
    "regional_demand_index",       # regional demand baseline multiplier
]
```

**Backward compatibility:** `to_model_matrix()` always reindexes onto `MODEL_FEATURES`,
filling absent columns with `0`. Payloads without weather fields continue to work exactly
as before — they just don't benefit from weather signals.

> [!IMPORTANT]
> **Model retraining required.** Any existing `training_models/hybrid_model.pkl` trained
> before Phase 6 will have the wrong feature vector shape. Run `make train` after
> pulling this change.

---

## 4. Migration Guide

### Step-by-step for an existing deployment

```bash
# 1. Pull the latest code
git pull

# 2. Install any new requirements (none added in Phase 6, but good practice)
make install

# 3. Verify db6 schema files are present
make schema-init
make schema-validate

# 4. Retrain the model with the updated feature set
make data        # only needed if synthetic_inventory_db_native.csv is missing
make train       # trains on existing CSV; weather features default to 0

# 5. Run the full test suite
make test

# 6. Run the pipeline
make run
```

### Using the full LFS dataset for weather-enriched training

If you have Git LFS and have pulled `synthetic_inventory_weather_region_v2_festival_demand.csv`
to the repo root, the `DataPreparation` class will automatically pick up the weather columns
during `make prepare` + `make train`. The resulting model will benefit from all 8 weather
features at training time, producing significantly better forecasts for weather/festival periods.

```bash
git lfs pull   # pull the 469 MB LFS file
make train     # re-prepare and retrain with full weather features
```

---

## 5. Makefile Usage Guide

```text
make help              — print this table
make venv              — create .venv (Python virtual environment)
make install           — pip install -r requirements.txt into .venv

make schema-init       — ensure db6 CSV files exist
make schema-validate   — verify all CSV headers are non-empty

make data              — generate synthetic_inventory_db_native.csv
make prepare           — clean data + engineer features (produces *.pkl)
make train             — train the Hybrid SARIMAX+XGBoost model

make test              — all offline tests (schema + policy + forecast + pipeline)
make test-schema       — pytest tests/test_weather_festival_schema.py
make test-policy       — pytest tests/test_policy_agent.py
make test-forecast     — python tests/test_demand_forecast_agent.py
make test-pipeline     — python tests/test_full_pipeline_integration.py

make lint              — flake8 (max-line 120)
make format            — black + isort (non-blocking)

make smoke-azure       — Azure OpenAI connectivity smoke test
make smoke-azure-pipeline — full pipeline run with Azure enabled

make run               — full pipeline run, Azure OFF
make serve             — uvicorn FastAPI dev server

make clean             — remove __pycache__, .pyc, pytest cache
make reset             — clean + remove trained model artifacts (keeps .venv)
make distclean         — reset + remove .venv and synthetic CSV

make all               — schema-init + data + prepare + train + test
```

---

## 6. Testing Guide

### Prerequisites

```bash
make venv install schema-init
```

### Offline tests (no Azure, no trained model needed)

```bash
# Schema + model tests (pytest-based, fastest)
make test-schema   # ~2s — 21 tests covering all db6 loaders, WeatherFestivalContext, risk scaling
make test-policy   # ~1s — 4 tests covering policy compliance + weather risk threshold tightening
```

### Model-dependent tests (require `make train` first)

```bash
make train            # ~2–5 min depending on dataset size
make test-forecast    # covers feature engineering parity + weather payload end-to-end
make test-pipeline    # full 5-agent pipeline with weather context check
```

### Expected outputs

**`make test-schema`:**
```
tests/test_weather_festival_schema.py::test_load_weather_festival_dataset... PASSED
tests/test_weather_festival_schema.py::test_load_demand_context_fact_returns_records PASSED
... (21 tests, 0 failed)
```

**`make test-policy`:**
```
tests/test_policy_agent.py::test_policy_agent_compliance PASSED
tests/test_policy_agent.py::test_policy_agent_weather_risk_tightens_reliability_threshold PASSED
tests/test_policy_agent.py::test_policy_agent_weather_risk_below_threshold_no_tightening PASSED
tests/test_policy_agent.py::test_policy_evaluation_service_backward_compat_no_weather_arg PASSED
```

**`make test-forecast`** (after training):
```
[PASS] weather/festival feature 'weather_demand_multiplier' in MODEL_FEATURES
[PASS] is_festival_day_int derived from is_festival_day=True
[PASS] weather-enriched payload: forecast completes without error
... (50+ tests)
```

**`make test-pipeline`** (after training):
```
[PASS] weather_context_loaded key present in pipeline result
[PASS] all assessments have weather_context attribute (None or WeatherFestivalContext)
... (25+ tests)
```

### Validation checkpoints

| Checkpoint | What to look for |
|---|---|
| `make schema-validate` | Zero errors; all CSV files show column counts |
| `make test-schema` | 21 passed, 0 failed |
| `make test-policy` | 4 passed, 0 failed |
| `make run` output | "Weather context entries loaded: N" where N > 0 |
| `run_outputs/pipeline_summary_*.json` | `weather_context_loaded` key present with integer value |

---

## 7. Architecture Diagram

```
CSV Data Sources
├── db1–db5 (existing)
└── db6 (NEW: demand_context_fact, festival_calendar, location_climate_profile)
        │
        ▼
CsvInventoryDataLoader.build_weather_context_map()
        │  dict: (sku_id, loc_id) → WeatherFestivalContext
        ▼
InventoryMonitoringAgent.execute()
        │  passes weather_context_map to risk service
        ▼
InventoryRiskMonitoringService.assess_risk()
        │  scales demand by effective_demand_multiplier()
        │  attaches WeatherFestivalContext to each RiskAssessment
        ▼
PipelineOrchestrator._build_forecast_payload()
        │  injects 8 weather fields into DemandForecastAgent payload
        ▼
DemandForecastAgent → FeatureEngineeringService
        │  derives is_festival_day_int, is_shopping_season_int, etc.
        │  MODEL_FEATURES now includes 8 weather/festival columns
        ▼
OrderCalculationService.generate_order()
        │  weather-adjusted EOQ, elevated priority for extreme weather
        ▼
PolicyEvaluationService.evaluate_supplier()
        │  tightened reliability threshold when weather_supply_risk > 0.6
        ▼
Pipeline Output (run_outputs/pipeline_summary_*.json)
        └── includes: weather_context_loaded, weather-adjusted orders
```
