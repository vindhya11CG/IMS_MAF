import logging
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add project root to Python path so agents and utils can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.v1.api import api_router
from api.core.state import state
from utils.csv_loader import CsvInventoryDataLoader
from utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="IMS + Demand Forecasting API",
    version="1.0.0",
    description=(
        "Production-grade Multi-Agent Inventory Management and Demand Forecasting API.\n\n"
        "**Key capabilities:**\n"
        "- Multi-agent inventory risk & replenishment workflow\n"
        "- Hybrid SARIMAX + XGBoost demand forecasting\n"
        "- Single and vectorized batch predictions\n"
        "- N-day rolling product forecasts\n"
        "- Inventory reorder and risk scoring\n"
        "- What-if scenario simulation\n\n"
        "All demand forecasting endpoints are under `/api/v1/forecasting/`."
    ),
    contact={"name": "IMS Engineering"},
    license_info={"name": "Private"},
)

# Allow frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup: configure logging, load CSV data, and warm the forecasting model."""
    setup_logging(logging.INFO, log_file="logs/api.log")
    logger.info("IMS API starting up. Loading CSV data into memory...")

    loader = CsvInventoryDataLoader()

    # Pre-load CSV data so inventory endpoints respond immediately
    try:
        snapshots = loader.load_inventory_daily_snapshots()
        positions = loader.load_inventory_positions()
        products = loader.load_products()
        product_categories = loader.load_product_categories()
        seasonal_patterns = loader.load_seasonal_patterns()
        locations = loader.load_locations()

        state.raw_data["snapshots"] = snapshots
        state.raw_data["positions"] = [
            p.__dict__ if hasattr(p, "__dict__") else p for p in positions
        ]
        state.raw_data["products"] = products
        state.raw_data["product_categories"] = product_categories
        state.raw_data["seasonal_patterns"] = seasonal_patterns
        state.raw_data["locations"] = locations
        logger.info(
            "Loaded %d snapshots, %d positions, %d products, %d categories, "
            "%d seasonal patterns, %d locations.",
            len(snapshots),
            len(positions),
            len(products),
            len(product_categories),
            len(seasonal_patterns),
            len(locations),
        )
    except Exception as exc:
        logger.error("Failed to load CSV data on startup: %s", exc)

    # Warm-up the forecasting model (loads hybrid_model.pkl into memory once)
    try:
        from demand_forecast_agent.services.core_forecasting_service import ModelLoaderService

        ModelLoaderService.load()
        state.mark_model_loaded()
        logger.info("Hybrid SARIMAX+XGBoost model loaded and cached in memory.")
    except Exception as exc:
        logger.error("Failed to load forecasting model on startup: %s", exc, exc_info=True)


app.include_router(api_router, prefix="/api/v1")
