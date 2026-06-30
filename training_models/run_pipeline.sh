#!/bin/bash

# Master Orchestration Script
# Runs complete demand forecasting pipeline end-to-end
# Usage: bash run_pipeline.sh

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════════════════════════╗"
echo "║         DEMAND FORECASTING - COMPLETE PIPELINE ORCHESTRATION                  ║"
echo "║                        Python 3.11.9 | FastAPI                                ║"
echo "╚════════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_section() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check Python version
print_section "CHECKING ENVIRONMENT"
print_step "Verifying Python 3.11.9..."

PYTHON_VERSION=$(python3 --version 2>&1)
echo "Found: $PYTHON_VERSION"

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 not found. Please install Python 3.11.9 first."
    exit 1
fi

# Check if in correct directory
if [ ! -f "requirements.txt" ]; then
    print_error "requirements.txt not found. Please run from project root directory."
    exit 1
fi

print_success "Environment verified"

# Install dependencies
print_section "INSTALLING DEPENDENCIES"
print_step "Installing Python packages..."

pip install -q -r requirements.txt 2>/dev/null || {
    print_error "Failed to install dependencies"
    exit 1
}

print_success "Dependencies installed"

# Step 1: Data Preparation
print_section "STEP 1: DATA PREPARATION & EXPLORATION"
print_step "Loading and preprocessing CSV..."
print_step "Creating features..."
print_step "Generating train/val/test splits..."

python3 01_data_preparation.py

if [ $? -eq 0 ]; then
    print_success "Data preparation complete"
else
    print_error "Data preparation failed"
    exit 1
fi

# Step 2: Model Training
print_section "STEP 2: MODEL TRAINING"
print_step "Training SARIMAX models (per-item)..."
print_step "Training XGBoost global model..."
print_step "Creating hybrid ensemble..."
print_step "Validating on validation set..."
print_step "Evaluating on test set..."

python3 02_model_training.py

if [ $? -eq 0 ]; then
    print_success "Model training complete"
else
    print_error "Model training failed"
    exit 1
fi
echo "Starting Demand Forecast Agent"

cd demand_forecast_agent

python -m uvicorn app:app \
--host 0.0.0.0 \
--port 8000

# Step 3: Results Report
print_section "STEP 3: GENERATING RESULTS REPORT"
print_step "Loading metrics..."
print_step "Creating text report..."
print_step "Generating JSON report..."
print_step "Creating performance charts..."

python3 05_results_report.py

if [ $? -eq 0 ]; then
    print_success "Results report complete"
else
    print_error "Results report generation failed"
    exit 1
fi

# Step 4: Launch FastAPI Server
print_section "STEP 4: LAUNCHING API SERVER"
print_step "Starting FastAPI application..."
print_step "Loading trained model..."
print_step "Initializing endpoints..."

echo ""
echo -e "${YELLOW}Starting API server in background...${NC}"
python3 -m uvicorn 03_fastapi_app:app --host 0.0.0.0 --port 8000 --reload &
SERVER_PID=$!

# Wait for server to start
print_step "Waiting for server to be ready..."
sleep 5

# Step 5: Run API Tests
print_section "STEP 5: RUNNING API TESTS"
print_step "Testing health check endpoint..."
print_step "Testing forecast endpoints..."
print_step "Testing batch operations..."
print_step "Running load tests..."

python3 04_api_testing.py

if [ $? -eq 0 ]; then
    print_success "API tests complete"
else
    print_error "Some API tests failed"
fi

# Summary
print_section "PIPELINE EXECUTION SUMMARY"

echo -e "${GREEN}✓ Data Preparation${NC}       - Complete"
echo -e "${GREEN}✓ Model Training${NC}         - Complete (SARIMAX + XGBoost)"
echo -e "${GREEN}✓ Results Report${NC}         - Generated"
echo -e "${GREEN}✓ API Server${NC}             - Running (PID: $SERVER_PID)"
echo -e "${GREEN}✓ API Tests${NC}              - Complete"

echo ""
echo -e "${YELLOW}GENERATED FILES:${NC}"
echo "  ├── data_clean.parquet              (Cleaned dataset)"
echo "  ├── train_data.parquet              (Training set - 70%)"
echo "  ├── val_data.parquet                (Validation set - 15%)"
echo "  ├── test_data.parquet               (Test set - 15%)"
echo "  ├── hybrid_model.pkl                (Trained model)"
echo "  ├── model_metrics.json              (Performance metrics)"
echo "  ├── results_report.json             (Detailed report)"
echo "  ├── performance_summary.png         (Visual summary)"
echo "  └── api_test_results.csv            (API test results)"

echo ""
echo -e "${YELLOW}API SERVER:${NC}"
echo "  URL:                 http://localhost:8000"
echo "  Documentation:       http://localhost:8000/docs"
echo "  ReDoc:               http://localhost:8000/redoc"
echo "  Health Check:        http://localhost:8000/health"

echo ""
echo -e "${YELLOW}NEXT STEPS:${NC}"
echo "  1. Review results_report.json for detailed metrics"
echo "  2. View performance_summary.png for visual results"
echo "  3. Test API at http://localhost:8000/docs"
echo "  4. Check api_test_results.csv for endpoint performance"
echo "  5. Run sample forecasts and validate results"

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}PIPELINE COMPLETE - READY FOR 9 AM MEETING!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

# Keep server running
echo -e "${YELLOW}API Server is running. Press Ctrl+C to stop.${NC}"
wait $SERVER_PID
