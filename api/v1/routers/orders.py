from fastapi import APIRouter, Depends
from api.core.state import AppState
from api.core.dependencies import get_app_state

router = APIRouter()

@router.get("/")
async def get_orders(state: AppState = Depends(get_app_state)):
    """Get all generated replenishment orders (Agent 2 Output)."""
    phase_4 = state.results.get("phase_4_results", {})
    return phase_4.get("orders", [])

@router.get("/summary")
async def get_orders_summary(state: AppState = Depends(get_app_state)):
    """Get the high-level math and breakdown of the orders."""
    phase_4 = state.results.get("phase_4_results", {})
    return phase_4.get("summary", {})
