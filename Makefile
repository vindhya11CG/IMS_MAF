# ==============================================================================
# Makefile - Inventory Management / Demand Forecasting System
# ==============================================================================
# Works on Linux/macOS natively. On Windows, run via WSL, Git Bash, or
# install GNU Make (choco install make) and use the .venv\Scripts Python.
#
# Recommended first-time developer workflow:
#   make venv install schema-init data prepare train test run
#
# Daily development workflow:
#   make test                  - run all offline tests
#   make run                   - run the full pipeline (no Azure)
#   make lint                  - check code style
# ==============================================================================

# -- Platform detection -------------------------------------------------------
ifeq ($(OS),Windows_NT)
    VENV_NAME := $(shell if exist venv (echo venv) else (echo .venv))
    VENV_BIN  := $(VENV_NAME)\Scripts
    PYTHON    := python
    RM_RF     := rd /s /q
    FIND_PYC  := del /s /q *.pyc 2>NUL || true
    MKDIR     := mkdir
else
    VENV_NAME := $(shell if [ -d "venv" ]; then echo "venv"; else echo ".venv"; fi)
    VENV_BIN  := $(VENV_NAME)/bin
    PYTHON    := python3
    RM_RF     := rm -rf
    FIND_PYC  := find . -type f -name "*.pyc" -delete
    MKDIR     := mkdir -p
endif

PIP      := $(VENV_BIN)/pip
PY       := $(VENV_BIN)/python
UVICORN  := $(VENV_BIN)/uvicorn
PYTEST   := $(VENV_BIN)/pytest
FLAKE8   := $(VENV_BIN)/flake8
BLACK    := $(VENV_BIN)/black
ISORT    := $(VENV_BIN)/isort

.PHONY: help venv install \
        schema-init schema-validate \
        data prepare train \
        test test-schema test-forecast test-pipeline test-policy \
        lint format \
        smoke-azure smoke-azure-pipeline \
        run serve \
        clean reset distclean all

# ==============================================================================
# help
# ==============================================================================
help:
	@echo ""
	@echo "============================================================"
	@echo " IMS-MAF  Inventory Management / Demand Forecasting System"
	@echo "============================================================"
	@echo ""
	@echo " Environment"
	@echo "  make venv                  Create virtual environment (.venv)"
	@echo "  make install               Install all requirements into .venv"
	@echo ""
	@echo " Schema"
	@echo "  make schema-init           Create db6 CSV files if absent"
	@echo "  make schema-validate       Validate all CSV header counts"
	@echo ""
	@echo " Data & Training"
	@echo "  make data                  Generate synthetic training CSV"
	@echo "  make prepare               Run data_preparation.py (clean+features)"
	@echo "  make train                 Train the Hybrid SARIMAX+XGBoost model"
	@echo ""
	@echo " Tests"
	@echo "  make test                  Run all offline test suites"
	@echo "  make test-schema           pytest tests/test_weather_festival_schema.py"
	@echo "  make test-policy           pytest tests/test_policy_agent.py"
	@echo "  make test-forecast         python tests/test_demand_forecast_agent.py"
	@echo "  make test-pipeline         python tests/test_full_pipeline_integration.py"
	@echo ""
	@echo " Code Quality"
	@echo "  make lint                  flake8 style check (E/W, max-line 120)"
	@echo "  make format                black + isort (auto-format, non-blocking)"
	@echo ""
	@echo " Azure Testing"
	@echo "  make smoke-azure           Verify Azure OpenAI connectivity"
	@echo "  make smoke-azure-pipeline  Full Azure-enabled pipeline demo run"
	@echo ""
	@echo " Run"
	@echo "  make run                   Full pipeline (Azure OFF, no cap)"
	@echo "  make serve                 FastAPI dev server (uvicorn --reload)"
	@echo ""
	@echo " Cleanup"
	@echo "  make clean                 Remove __pycache__, .pyc, test artifacts"
	@echo "  make reset                 clean + remove trained model artifacts"
	@echo "  make distclean             reset + remove .venv and synthetic data"
	@echo "  make all                   schema-init + data + prepare + train + test"
	@echo ""

# ==============================================================================
# Environment
# ==============================================================================
venv:
	$(PYTHON) -m venv .venv
	@echo ""
	@echo "Virtual environment created at .venv/"
	@echo "Activate with:"
	@echo "  source .venv/bin/activate      (Linux/macOS)"
	@echo "  .venv\\Scripts\\activate         (Windows cmd)"
	@echo "  .venv/Scripts/Activate.ps1     (Windows PowerShell)"

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "All requirements installed."

# ==============================================================================
# Schema
# ==============================================================================
schema-init:
	@echo "[schema-init] Checking db6 CSV files..."
	@$(PY) -c "\
import os, pathlib; \
db6 = pathlib.Path('data/csv_exports/db6_csv_export'); \
db6.mkdir(parents=True, exist_ok=True); \
files = ['demand_context_fact.csv', 'festival_calendar.csv', 'location_climate_profile.csv']; \
missing = [f for f in files if not (db6 / f).exists()]; \
print(f'  Present : {len(files) - len(missing)}/{len(files)} db6 files'); \
print(f'  Missing : {missing}' if missing else '  All db6 CSV files are present.') \
"
	@echo "[schema-init] Done."

schema-validate:
	@echo "[schema-validate] Checking CSV header integrity..."
	@$(PY) -c "\
import csv, pathlib, sys; \
errors = []; \
root = pathlib.Path('data/csv_exports'); \
for csv_file in sorted(root.rglob('*.csv')): \
    try: \
        with open(csv_file, encoding='utf-8') as f: \
            reader = csv.reader(f); \
            header = next(reader, []); \
        if len(header) == 0: \
            errors.append(f'EMPTY HEADER: {csv_file}'); \
        else: \
            print(f'  OK  {csv_file.relative_to(root)}  ({len(header)} cols)'); \
    except Exception as e: \
        errors.append(f'ERROR {csv_file}: {e}'); \
if errors: \
    print('\\nVALIDATION FAILURES:'); \
    [print(f'  {e}') for e in errors]; \
    sys.exit(1); \
else: \
    print('\\nAll CSV files have valid headers.') \
"

# ==============================================================================
# Data & Training
# ==============================================================================
data:
	$(PY) training_models/generate_synthetic_dataset.py

prepare:
	$(PY) training_models/data_preparation.py

train: prepare
	$(PY) training_models/model_training.py

# ==============================================================================
# Tests
# ==============================================================================
test: test-schema test-policy test-forecast test-pipeline
	@echo ""
	@echo "All test suites completed."

test-schema:
	@echo ""
	@echo "--- pytest: test_weather_festival_schema.py ---"
	$(PYTEST) tests/test_weather_festival_schema.py -v

test-policy:
	@echo ""
	@echo "--- pytest: test_policy_agent.py ---"
	$(PYTEST) tests/test_policy_agent.py -v

test-forecast:
	@echo ""
	@echo "--- script: test_demand_forecast_agent.py ---"
	$(PY) tests/test_demand_forecast_agent.py

test-pipeline:
	@echo ""
	@echo "--- script: test_full_pipeline_integration.py ---"
	$(PY) tests/test_full_pipeline_integration.py

# ==============================================================================
# Code Quality
# ==============================================================================
lint:
	$(FLAKE8) agents/ demand_forecast_agent/ orchestration/ utils/ training_models/ \
	    --max-line-length=120 \
	    --extend-ignore=E203,W503,E501 \
	    --exclude=__pycache__,.venv,venv

format:
	-$(BLACK) agents/ demand_forecast_agent/ orchestration/ utils/ training_models/ tests/ \
	    --line-length=120
	-$(ISORT) agents/ demand_forecast_agent/ orchestration/ utils/ training_models/ tests/ \
	    --profile=black

# ==============================================================================
# Azure Testing
# ==============================================================================
smoke-azure:
	$(PY) tests/manual_azure_smoke_test.py

# Full Azure-enabled pipeline run (no artificial MAX_ML_FORECAST_CALLS cap)
smoke-azure-pipeline:
	$(PY) tests/manual_full_pipeline_azure_test.py

# ==============================================================================
# Run
# ==============================================================================
# Full pipeline run, Azure off, no artificial cap on ML forecast calls.
run:
	$(PY) orchestration/pipeline_orchestrator.py

serve:
	$(UVICORN) api.app:app --reload

# ==============================================================================
# Cleanup
# ==============================================================================
clean:
ifeq ($(OS),Windows_NT)
	-for /d /r . %%d in (__pycache__) do @rd /s /q "%%d" 2>NUL
	-del /s /q *.pyc 2>NUL
	-rd /s /q .pytest_cache 2>NUL
else
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf logs/*.log .pytest_cache 2>/dev/null || true
endif

reset: clean
	-$(RM_RF) training_models/hybrid_model.pkl
	-$(RM_RF) training_models/train_data.pkl
	-$(RM_RF) training_models/val_data.pkl
	-$(RM_RF) training_models/test_data.pkl
	-$(RM_RF) training_models/data_clean.pkl
	-$(RM_RF) training_models/model_metrics.json
	-$(RM_RF) training_models/model_features.json
	@echo "Trained model artifacts removed. Run 'make train' to retrain."

distclean: reset
	-$(RM_RF) .venv
	-$(RM_RF) venv
	-$(RM_RF) synthetic_inventory_db_native.csv
	@echo "Full clean complete. Run 'make venv install' to start fresh."

# ==============================================================================
# Composite
# ==============================================================================
all: schema-init data prepare train test