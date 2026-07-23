"""Supplier master data and supplier analytics endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from utils.csv_loader import CsvInventoryDataLoader

router = APIRouter()


def _load_supplier_view() -> Dict[str, List[Dict[str, Any]]]:
    loader = CsvInventoryDataLoader()
    suppliers = loader.load_suppliers()
    performance = loader.load_supplier_performance_metrics()
    pricing = loader.load_supplier_pricing_tiers()
    category_map = loader.load_supplier_category_mapping()
    risk_profile = loader.load_supplier_risk_profile()

    return {
        "suppliers": suppliers,
        "performance": performance,
        "pricing": pricing,
        "category_map": category_map,
        "risk_profile": risk_profile,
    }


@router.get("/", summary="List suppliers")
async def list_suppliers(
    country_code: Optional[str] = Query(None, description="Optional country filter")
) -> List[Dict[str, Any]]:
    data = _load_supplier_view()
    suppliers = data["suppliers"]

    if country_code:
        suppliers = [
            supplier
            for supplier in suppliers
            if str(supplier.get("country_code", "")).upper() == country_code.upper()
        ]

    return suppliers


@router.get("/{supplier_id}", summary="Get supplier by id")
async def get_supplier(supplier_id: int) -> Dict[str, Any]:
    data = _load_supplier_view()
    for supplier in data["suppliers"]:
        if int(supplier.get("supplier_id", -1)) == supplier_id:
            return supplier
    raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")


@router.get("/performance", summary="List supplier performance metrics")
async def list_supplier_performance() -> List[Dict[str, Any]]:
    return _load_supplier_view()["performance"]


@router.get("/pricing-tiers", summary="List supplier pricing tiers")
async def list_supplier_pricing_tiers() -> List[Dict[str, Any]]:
    return _load_supplier_view()["pricing"]


@router.get("/risk-profile", summary="List supplier risk profile data")
async def list_supplier_risk_profile() -> List[Dict[str, Any]]:
    return _load_supplier_view()["risk_profile"]
