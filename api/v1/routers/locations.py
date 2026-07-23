"""Locations API router — read endpoints for store and DC location data.

Exposes endpoints sourced from DB1 CSV exports:
- locations.csv
- stores.csv
- states.csv
"""

from __future__ import annotations

import csv
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from utils.csv_loader import CsvInventoryDataLoader

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: Dict[str, Any] = {}
_cache_loaded_at: Optional[datetime] = None
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 600

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class LocationResponse(BaseModel):
    """A single warehouse / store / distribution-centre record."""
    model_config = ConfigDict(from_attributes=True)

    location_id: int = Field(...)
    location_type: Optional[str] = Field(None)
    location_name: Optional[str] = Field(None)
    state_id: Optional[Any] = Field(None)
    city: Optional[str] = Field(None)
    state_name: Optional[str] = Field(None)
    state_code: Optional[str] = Field(None)
    country_code: Optional[str] = Field(None)
    country: Optional[str] = Field(None)


class StoreResponse(BaseModel):
    """A rich store record."""
    model_config = ConfigDict(from_attributes=True)

    store_id: int = Field(...)
    store_code: Optional[str] = Field(None)
    store_name: Optional[str] = Field(None)
    city: Optional[str] = Field(None)
    state_id: Optional[Any] = Field(None)
    format_id: Optional[int] = Field(None)
    dc_id: Optional[int] = Field(None)
    opening_date: Optional[str] = Field(None)
    active_flag: Optional[bool] = Field(None)
    state_name: Optional[str] = Field(None)
    country_code: Optional[str] = Field(None)
    country: Optional[str] = Field(None)


def _derive_country_info(state_abbrev: str) -> tuple[str, str]:
    if not state_abbrev:
        return "US", "United States"
    if "-" in state_abbrev:
        code = state_abbrev.split("-")[0].upper()
        if code == "IN":
            return "IN", "India"
        if code == "SE":
            return "SE", "Sweden"
        return code, code
    return "US", "United States"


def _load_data() -> Dict[str, Any]:
    loader = CsvInventoryDataLoader()
    
    states_raw = loader.load_states()
    states_map = {}
    for s in states_raw:
        sa = s.get("state_code", "")
        cc, c = _derive_country_info(sa)
        states_map[str(s["state_id"]).zfill(2)] = {
            "state_name": s.get("state_name", ""),
            "state_code": sa,
            "country_code": cc,
            "country": c
        }
        # Also map integer just in case
        states_map[str(int(s["state_id"]))] = states_map[str(s["state_id"]).zfill(2)]

    locations_raw = loader.load_locations()
    for loc in locations_raw:
        sid = str(loc.get("state_id", ""))
        sinfo = states_map.get(sid) or states_map.get(sid.zfill(2), {})
        loc["state_name"] = sinfo.get("state_name")
        loc["state_code"] = sinfo.get("state_code")
        loc["country_code"] = sinfo.get("country_code")
        loc["country"] = sinfo.get("country")

    stores_raw = loader.load_stores()
    for store in stores_raw:
        sid = str(store.get("state_id", ""))
        sinfo = states_map.get(sid) or states_map.get(sid.zfill(2), {})
        store["state_name"] = sinfo.get("state_name")
        store["country_code"] = sinfo.get("country_code")
        store["country"] = sinfo.get("country")

    return {
        "locations": locations_raw,
        "stores": stores_raw,
        "states_map": states_map
    }


def _get_data() -> Dict[str, Any]:
    global _cache, _cache_loaded_at
    now = datetime.now(tz=timezone.utc)
    if _cache_loaded_at is not None and (now - _cache_loaded_at).total_seconds() < _CACHE_TTL_SECONDS:
        return _cache
    with _cache_lock:
        now = datetime.now(tz=timezone.utc)
        if _cache_loaded_at is None or (now - _cache_loaded_at).total_seconds() >= _CACHE_TTL_SECONDS:
            _cache = _load_data()
            _cache_loaded_at = now
    return _cache


@router.get("/", response_model=List[LocationResponse])
async def list_locations(
    location_type: Optional[str] = Query(None),
    country_code: Optional[str] = Query(None)
) -> List[LocationResponse]:
    data = _get_data()
    rows = data["locations"]
    if location_type:
        rows = [r for r in rows if str(r.get("location_type")).upper() == location_type.upper()]
    if country_code:
        rows = [r for r in rows if str(r.get("country_code", "")).upper() == country_code.upper()]
    return [LocationResponse(**r) for r in rows]


@router.get("/stores", response_model=List[StoreResponse])
async def list_stores(
    country_code: Optional[str] = Query(None)
) -> List[StoreResponse]:
    data = _get_data()
    rows = data["stores"]
    if country_code:
        rows = [r for r in rows if str(r.get("country_code", "")).upper() == country_code.upper()]
    return [StoreResponse(**r) for r in rows]


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(location_id: int) -> LocationResponse:
    data = _get_data()
    for loc in data["locations"]:
        if loc["location_id"] == location_id:
            return LocationResponse(**loc)
    raise HTTPException(status_code=404, detail=f"Location {location_id} not found.")
