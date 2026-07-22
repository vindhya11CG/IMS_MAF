from fastapi import APIRouter
from .routers import (
    agent,
    forecasting,
    inventory,
    locations,
    orders,
    products,
    purchase_history,
    risks,
    simulation,
    weather,
)

api_router = APIRouter()

api_router.include_router(agent.router, prefix="/agent", tags=["Agent Operations (Control Panel)"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory (Agent 1 Inputs)"])
api_router.include_router(risks.router, prefix="/risks", tags=["Risks (Agent 1 Output -> Agent 2 Input)"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders (Agent 2 Outputs)"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(locations.router, prefix="/locations", tags=["Locations"])
api_router.include_router(
    purchase_history.router,
    prefix="/purchase-history",
    tags=["Purchase History Analytics"],
)
api_router.include_router(
    simulation.router,
    prefix="/simulation",
    tags=["Simulation"],
)

# --- Weather & Festival Context endpoints ---
api_router.include_router(
    weather.router,
    prefix="/weather",
    tags=["Weather & Festival Context"],
)

# --- Demand Forecasting endpoints ---
api_router.include_router(
    forecasting.router,
    prefix="/forecasting",
    tags=["Demand Forecasting"],
)
