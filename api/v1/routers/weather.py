"""Weather and festival demand context router for FastAPI backend.

Exposes endpoints for the frontend team to query weather context facts,
festival calendar entries, and location climate profiles.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query

from api.core.dependencies import get_app_state
from api.core.state import AppState
from utils.csv_loader import CsvInventoryDataLoader

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/context", summary="Get weather and festival demand context facts")
async def get_weather_context(
    product_id: Optional[int] = Query(None, description="Filter by product/SKU ID"),
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    state: AppState = Depends(get_app_state),
) -> Dict[str, Any]:
    """Retrieve weather & festival demand context records (from db6 demand_context_fact)."""
    context = state.raw_data.get("demand_context", [])
    if not context:
        loader = CsvInventoryDataLoader()
        context = loader.load_demand_context_fact()
        state.raw_data["demand_context"] = context

    filtered = context
    if product_id is not None:
        filtered = [r for r in filtered if r.get("product_id") == product_id]
    if location_id is not None:
        filtered = [r for r in filtered if r.get("location_id") == location_id]

    return {"count": len(filtered), "data": filtered}


@router.get("/festivals", summary="Get festival calendar entries")
async def get_festivals(
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    state: AppState = Depends(get_app_state),
) -> Dict[str, Any]:
    """Retrieve festival calendar reference table entries."""
    festivals = state.raw_data.get("festival_calendar", [])
    if not festivals:
        loader = CsvInventoryDataLoader()
        festivals = loader.load_festival_calendar()
        state.raw_data["festival_calendar"] = festivals

    if location_id is not None:
        festivals = [f for f in festivals if f.get("location_id") == location_id]

    return {"count": len(festivals), "data": festivals}


@router.get("/climate-profiles", summary="Get location climate profiles")
async def get_climate_profiles(
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    state: AppState = Depends(get_app_state),
) -> Dict[str, Any]:
    """Retrieve location climate profile table entries."""
    profiles = state.raw_data.get("climate_profiles", [])
    if not profiles:
        loader = CsvInventoryDataLoader()
        profiles = loader.load_location_climate_profile()
        state.raw_data["climate_profiles"] = profiles

    if location_id is not None:
        profiles = [p for p in profiles if p.get("location_id") == location_id]

    return {"count": len(profiles), "data": profiles}
