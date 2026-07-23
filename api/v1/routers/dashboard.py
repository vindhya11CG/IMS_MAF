"""Dashboard summary endpoints for the FastAPI backend."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from utils.csv_loader import CsvInventoryDataLoader

router = APIRouter()


@router.get("/overview", summary="Get dashboard overview counts")
async def dashboard_overview() -> Dict[str, Any]:
    loader = CsvInventoryDataLoader()

    products = loader.load_products()
    locations = loader.load_locations()
    stores = loader.load_stores()
    suppliers = loader.load_suppliers()
    supplier_risk = loader.load_supplier_risk_profile()

    return {
        "counts": {
            "products": len(products),
            "locations": len(locations),
            "stores": len(stores),
            "suppliers": len(suppliers),
            "supplier_risk_profiles": len(supplier_risk),
        },
        "status": "ok",
    }


@router.get("/summary", summary="Get a lightweight dashboard summary payload")
async def dashboard_summary() -> Dict[str, Any]:
    overview = await dashboard_overview()
    return {
        "summary": overview["counts"],
        "status": overview["status"],
    }
