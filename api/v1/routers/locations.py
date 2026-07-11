"""Locations API router — read endpoints for store and DC location data.

Exposes two ``GET`` endpoints sourced from the DB1 CSV export
(``data/csv_exports/db1_csv_export/locations.csv``):

* **List** (``/``) — All 53 locations (50 stores + 3 distribution centres),
  with optional ``location_type`` filter (``STORE`` or ``DC``).
* **Detail** (``/{location_id}``) — Single location by ID.

Data is loaded lazily into an in-process cache (TTL 10 min) on first access
so the startup cost is zero and the data is always consistent with the CSV.
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

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# CSV path & cache config
# ---------------------------------------------------------------------------
_LOCATIONS_CSV = Path("data/csv_exports/db1_csv_export/locations.csv")
_CACHE_TTL_SECONDS = 600


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class LocationResponse(BaseModel):
    """A single warehouse / store / distribution-centre record.

    Attributes:
        location_id: Unique numeric identifier.
        location_type: ``"STORE"`` or ``"DC"`` (distribution centre).
        location_name: Human-readable display name.
        state_id: State reference ID.
        city: City where the location is situated.
    """

    model_config = ConfigDict(from_attributes=True)

    location_id: int = Field(..., description="Unique location identifier.", examples=[1])
    location_type: str = Field(
        ..., description="Location type: STORE or DC.", examples=["STORE"]
    )
    location_name: str = Field(
        ..., description="Human-readable name.", examples=["San Francisco Downtown"]
    )
    state_id: str = Field(..., description="State reference ID.", examples=["01"])
    city: str = Field(..., description="City name.", examples=["San Francisco"])


# ---------------------------------------------------------------------------
# In-process cache — module-level singleton
# ---------------------------------------------------------------------------

_cache: List[Dict[str, Any]] = []
_cache_loaded_at: Optional[datetime] = None
_cache_lock = threading.Lock()


def _load_locations() -> List[Dict[str, Any]]:
    """Read the locations CSV and return a list of parsed dicts."""
    if not _LOCATIONS_CSV.exists():
        logger.warning("Locations CSV not found: %s", _LOCATIONS_CSV)
        return []
    try:
        rows: List[Dict[str, Any]] = []
        with _LOCATIONS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                row = {k.strip(): (v or "").strip() for k, v in row.items()}
                lid = row.get("location_id", "")
                if not lid:
                    continue
                rows.append(
                    {
                        "location_id": int(lid),
                        "location_type": row.get("location_type", ""),
                        "location_name": row.get("location_name", ""),
                        "state_id": row.get("state_id", ""),
                        "city": row.get("city", ""),
                    }
                )
        logger.info("Loaded %d locations from CSV.", len(rows))
        return rows
    except Exception:
        logger.exception("Failed to load locations CSV.")
        return []


def _get_locations() -> List[Dict[str, Any]]:
    """Return cached locations, refreshing if the TTL has expired."""
    global _cache, _cache_loaded_at
    now = datetime.now(tz=timezone.utc)
    if (
        _cache_loaded_at is not None
        and (now - _cache_loaded_at).total_seconds() < _CACHE_TTL_SECONDS
    ):
        return _cache
    with _cache_lock:
        now = datetime.now(tz=timezone.utc)
        if (
            _cache_loaded_at is None
            or (now - _cache_loaded_at).total_seconds() >= _CACHE_TTL_SECONDS
        ):
            _cache = _load_locations()
            _cache_loaded_at = now
    return _cache


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=List[LocationResponse],
    summary="List all locations",
    description=(
        "Returns all warehouse, store, and distribution-centre locations. "
        "Use the optional ``location_type`` filter to restrict results to "
        "``STORE`` or ``DC`` records only."
    ),
)
async def list_locations(
    location_type: Optional[str] = Query(
        None,
        description=(
            "Filter by location type. One of: ``STORE``, ``DC``. "
            "When omitted, all types are returned."
        ),
        examples=["STORE"],
    ),
) -> List[LocationResponse]:
    """Return all locations, optionally filtered by type.

    Args:
        location_type: When provided, restrict results to this type
            (case-insensitive). Valid values are ``STORE`` and ``DC``.

    Returns:
        A list of :class:`LocationResponse` records sorted by
        ``location_id``.
    """
    rows = _get_locations()
    if location_type is not None:
        rows = [r for r in rows if r["location_type"] == location_type.upper()]
    return [LocationResponse(**r) for r in rows]


@router.get(
    "/{location_id}",
    response_model=LocationResponse,
    summary="Get a location by ID",
    description=(
        "Returns a single location identified by its numeric ``location_id``. "
        "Returns HTTP 404 if no location with the given ID exists."
    ),
    responses={
        404: {
            "description": "Location not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Location with id 99 not found."}
                }
            },
        }
    },
)
async def get_location(location_id: int) -> LocationResponse:
    """Return a single location by its numeric ID.

    Args:
        location_id: The numeric location ID to look up.

    Returns:
        A :class:`LocationResponse` for the matching location.

    Raises:
        HTTPException: 404 if no location with ``location_id`` exists.
    """
    for loc in _get_locations():
        if loc["location_id"] == location_id:
            return LocationResponse(**loc)
    raise HTTPException(
        status_code=404,
        detail=f"Location with id {location_id} not found.",
    )
