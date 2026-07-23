"""Weather and festival demand context router for FastAPI backend."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query

from api.core.dependencies import get_app_state
from api.core.state import AppState
from utils.csv_loader import CsvInventoryDataLoader

logger = logging.getLogger(__name__)
router = APIRouter()

def _get_country_code_map(loader: CsvInventoryDataLoader) -> Dict[int, str]:
    # loc_id -> country_code
    locations = loader.load_locations()
    states = loader.load_states()
    state_to_cc = {}
    for s in states:
        sa = s.get("state_code", "")
        if "-" in sa:
            state_to_cc[s["state_id"]] = sa.split("-")[0].upper()
        else:
            state_to_cc[s["state_id"]] = "US"
    
    loc_to_cc = {}
    for loc in locations:
        loc_to_cc[loc["location_id"]] = state_to_cc.get(loc["state_id"], "US")
    return loc_to_cc

@router.get("/context", summary="Get weather and festival demand context facts")
async def get_weather_context(
    product_id: Optional[int] = Query(None, description="Filter by product/SKU ID"),
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    state: AppState = Depends(get_app_state),
) -> Dict[str, Any]:
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
    country_code: Optional[str] = Query(None, description="Filter by country code (US, IN, SE)"),
    state: AppState = Depends(get_app_state),
) -> Dict[str, Any]:
    festivals = state.raw_data.get("festival_calendar", [])
    loader = CsvInventoryDataLoader()
    if not festivals:
        festivals = loader.load_festival_calendar()
        state.raw_data["festival_calendar"] = festivals

    if location_id is not None:
        festivals = [f for f in festivals if f.get("location_id") == location_id]
        
    if country_code is not None:
        cc_map = _get_country_code_map(loader)
        festivals = [f for f in festivals if cc_map.get(f.get("location_id")) == country_code.upper()]

    return {"count": len(festivals), "data": festivals}


@router.get("/climate-profiles", summary="Get location climate profiles")
async def get_climate_profiles(
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    country_code: Optional[str] = Query(None, description="Filter by country code (US, IN, SE)"),
    state: AppState = Depends(get_app_state),
) -> Dict[str, Any]:
    profiles = state.raw_data.get("climate_profiles", [])
    loader = CsvInventoryDataLoader()
    if not profiles:
        profiles = loader.load_location_climate_profile()
        state.raw_data["climate_profiles"] = profiles

    if location_id is not None:
        profiles = [p for p in profiles if p.get("location_id") == location_id]
        
    if country_code is not None:
        cc_map = _get_country_code_map(loader)
        profiles = [p for p in profiles if cc_map.get(p.get("location_id")) == country_code.upper()]

    return {"count": len(profiles), "data": profiles}
