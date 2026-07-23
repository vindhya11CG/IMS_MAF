"""Regions API router — geographic data and distribution centers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from utils.csv_loader import CsvInventoryDataLoader

router = APIRouter()

def _derive_country(state_code: str) -> tuple[str, str]:
    if not state_code: return "US", "United States"
    if "-" in state_code:
        cc = state_code.split("-")[0].upper()
        if cc == "IN": return "IN", "India"
        if cc == "SE": return "SE", "Sweden"
        return cc, cc
    return "US", "United States"

@router.get("/countries", summary="List unique countries")
async def list_countries() -> List[Dict[str, str]]:
    loader = CsvInventoryDataLoader()
    states = loader.load_states()
    countries = set()
    for s in states:
        cc, c = _derive_country(s.get("state_code", ""))
        countries.add((cc, c))
    return [{"country_code": cc, "country_name": c} for cc, c in sorted(list(countries))]

@router.get("/states", summary="List states and provinces")
async def list_states(
    country_code: Optional[str] = Query(None, description="Filter by country code")
) -> List[Dict[str, Any]]:
    loader = CsvInventoryDataLoader()
    states = loader.load_states()
    result = []
    for s in states:
        cc, c = _derive_country(s.get("state_code", ""))
        if country_code and cc != country_code.upper():
            continue
        s["country_code"] = cc
        s["country"] = c
        result.append(s)
    return result

@router.get("/distribution-centers", summary="List all distribution centers")
async def list_dcs(
    country_code: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    loader = CsvInventoryDataLoader()
    dcs = loader.load_distribution_centers()
    states = loader.load_states()
    state_to_cc = {s["state_id"]: _derive_country(s.get("state_code", ""))[0] for s in states}
    
    result = []
    for dc in dcs:
        cc = state_to_cc.get(dc["state_id"], "US")
        if country_code and cc != country_code.upper():
            continue
        dc["country_code"] = cc
        result.append(dc)
    return result
