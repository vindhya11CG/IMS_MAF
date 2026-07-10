# ==============================================================================
# Makefile - Inventory Management / Demand Forecasting System
# ==============================================================================
# Works on Linux/macOS natively. On Windows, run via WSL or Git Bash (or
# install GNU Make via chocolatey: `choco install make`).
#
# Quick start:
#   make venv install data prepare train test run
# ==============================================================================

ifeq ($(OS),Windows_NT)
    VENV_BIN := venv/Scripts
    PYTHON   := python
else
    VENV_BIN := venv/bin
    PYTHON   := python3
endif

PIP    := $(VENV_BIN)/pip
PY     := $(VENV_BIN)/python
UVICORN := $(VENV_BIN)/uvicorn

.PHONY: help venv install data prepare train test test-forecast test-pipeline \
        smoke-azure smoke-azure-pipeline run serve clean distclean all

help:
	@echo "Available targets:"
	@echo "  make venv                 - create a virtual environment in ./venv"
	@echo "  make install              - install requirements.txt into the venv"
	@echo "  make data                 - generate the synthetic training dataset"
	@echo "  make prepare              - run data_preparation.py (clean + feature-engineer + split)"
	@echo "  make train                - train the Hybrid SARIMAX+XGBoost model"
	@echo "  make test                 - run both offline test suites"
	@echo "  make test-forecast        - run only tests/test_demand_forecast_agent.py"
	@echo "  make test-pipeline        - run only tests/test_full_pipeline_integration.py"
	@echo "  make smoke-azure          - verify Azure OpenAI connectivity (requires .env)"
	@echo "  make smoke-azure-pipeline - run the full pipeline once with Azure enabled"
	@echo "  make run                  - run the full 5-agent pipeline (no Azure, full cap)"
	@echo "  make serve                - start the FastAPI app with uvicorn --reload"
	@echo "  make clean                - remove __pycache__, logs, and test artifacts"
	@echo "  make distclean            - clean + remove venv and trained model artifacts"
	@echo "  make all                  - data + prepare + train + test (fresh full setup)"

venv:
	$(PYTHON) -m venv venv
	@echo "Virtual environment created. Activate it with:"
	@echo "  source $(VENV_BIN)/activate   (Linux/macOS)"
	@echo "  $(VENV_BIN)\\activate          (Windows)"

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

data:
	$(PY) training_models/generate_synthetic_dataset.py

prepare:
	$(PY) training_models/data_preparation.py

train: prepare
	$(PY) training_models/model_training.py

test: test-forecast test-pipeline

test-forecast:
	$(PY) tests/test_demand_forecast_agent.py

test-pipeline:
	$(PY) tests/test_full_pipeline_integration.py

smoke-azure:
	$(PY) tests/manual_azure_smoke_test.py

# Intentionally does NOT cap MAX_ML_FORECAST_CALLS low - that's only for the
# fast smoke-test variant. This is meant as a real, Azure-enabled run.
smoke-azure-pipeline:
	$(PY) tests/manual_full_pipeline_azure_smoke_test.py

# Full pipeline run, Azure off, no artificial cap on ML forecast calls
# (uses the orchestrator's own default of 200, or your .env override).
run:
	$(PY) orchestration/pipeline_orchestrator.py

serve:
	$(UVICORN) api.app:app --reload

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf logs/*.log .pytest_cache 2>/dev/null || true

distclean: clean
	rm -rf venv
	rm -f training_models/hybrid_model.pkl \
	      training_models/train_data.pkl \
	      training_models/val_data.pkl \
	      training_models/test_data.pkl \
	      training_models/data_clean.pkl \
	      training_models/model_metrics.json \
	      training_models/model_features.json \
	      synthetic_inventory_db_native.csv

all: data prepare train test

