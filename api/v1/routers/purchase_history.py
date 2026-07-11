"""Purchase-history analytics router.

Exposes three ``GET`` endpoints that analyse how products have been **bought
(sold)** over standard rolling time windows anchored to the last date present
in the inventory snapshot dataset:

* **Summary** (``/summary``) — Aggregated units sold across the 1-month,
  3-month, 6-month, and full-dataset windows for every product, with optional
  filtering by location or category.

* **Product detail** (``/product/{product_id}``) — A per-product breakdown of
  purchase metrics across all four time windows, optionally filtered by
  location.

* **Top products** (``/top-products``) — Ranked list of the top-N products by
  units sold for a user-specified time window, with optional filtering by
  location or category.

All endpoints derive their time windows from the **last date present in the
data** (not the current wall-clock time), so results are always consistent
with the available dataset.  The full-dataset "last timeline" label is
computed dynamically: ``"1 year"`` when the dataset spans fewer than five
years, ``"5 years"`` otherwise.

Data is served from an in-memory cache (:class:`PurchaseHistoryService`) that
lazily loads CSV files on first access and refreshes every 10 minutes.

.. note::
    The ``/product/{product_id}`` path is a dynamic route and **must** be
    declared after the static ``/summary`` and ``/top-products`` routes to
    prevent FastAPI from interpreting those path segments as an integer
    ``product_id``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.v1.schemas.purchase_history import (
    DatasetMetadata,
    ProductPurchaseHistoryResponse,
    ProductWindowDetail,
    PurchaseHistorySummaryResponse,
    PurchaseSummaryItem,
    TopProductsResponse,
    WindowSummary,
)
from api.v1.services.purchase_history_service import (
    PurchaseHistoryService,
    get_purchase_history_service,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WINDOW_CONFIGS: list[tuple[str, int]] = [
    ("1 month", 30),
    ("3 months", 90),
    ("6 months", 180),
]
_DEFAULT_LIMIT: int = 10
_MAX_LIMIT: int = 100

# Valid ``window`` query-param values for /top-products.
_WindowParam = Literal["1m", "3m", "6m", "all"]

_WINDOW_PARAM_MAP: dict[str, int] = {
    "1m": 30,
    "3m": 90,
    "6m": 180,
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_dataset_metadata(service: PurchaseHistoryService) -> DatasetMetadata:
    """Construct a :class:`DatasetMetadata` from the service's date range.

    Args:
        service: The injected :class:`PurchaseHistoryService` instance.

    Returns:
        A :class:`DatasetMetadata` instance populated with first date, last
        date, timeline label, and total snapshot days.
    """
    first, last = service.get_dataset_date_range()
    total_days = (last - first).days + 1
    return DatasetMetadata(
        first_date=first,
        last_date=last,
        timeline_label=service.get_timeline_label(),
        total_snapshot_days=total_days,
    )


def _build_window_summary(
    service: PurchaseHistoryService,
    window_label: str,
    window_days: int,
    *,
    product_id: Optional[int] = None,
    category_id: Optional[int] = None,
) -> WindowSummary:
    """Compute a :class:`WindowSummary` for a single time window.

    Args:
        service: The injected :class:`PurchaseHistoryService` instance.
        window_label: Human-readable label (e.g. ``"1 month"``).
        window_days: Number of calendar days in the window.
        product_id: Optional SKU filter.
        category_id: Optional category filter.

    Returns:
        A fully populated :class:`WindowSummary` instance.
    """
    _, last = service.get_dataset_date_range()
    window_start = last - timedelta(days=window_days - 1)

    raw = service.get_window_summary(
        window_days,
        product_id=product_id,
        category_id=category_id,
    )

    items = [PurchaseSummaryItem(**r) for r in raw]
    products_with_sales = sum(1 for i in items if i.total_units_sold > 0)
    grand_total = sum(i.total_units_sold for i in items)

    return WindowSummary(
        window_label=window_label,
        window_days=window_days,
        window_start_date=window_start,
        window_end_date=last,
        total_products_with_sales=products_with_sales,
        grand_total_units_sold=grand_total,
        items=items,
    )


def _build_filter_description(
    category_id: Optional[int],
) -> Optional[str]:
    """Compose a human-readable filter description string.

    Args:
        category_id: Applied category filter, or ``None``.

    Returns:
        A comma-separated filter string (e.g. ``"location_id=5, category_id=1"``),
        or ``None`` when no filters were applied.
    """
    parts: list[str] = []
    if category_id is not None:
        parts.append(f"category_id={category_id}")
    return ", ".join(parts) if parts else None


# ============================================================================
# /summary — all four windows
# ============================================================================


@router.get(
    "/summary",
    response_model=PurchaseHistorySummaryResponse,
    summary="Purchase history summary across all time windows",
    description=(
        "Returns aggregated purchase (sales) metrics for **all four standard "
        "time windows** — 1 month, 3 months, 6 months, and the full dataset "
        "timeline — in a single response.\n\n"
        "Each window is anchored to the **last date present in the inventory "
        "snapshot dataset** (not today's wall-clock date), ensuring results "
        "are always consistent with the available data.\n\n"
        "The full-dataset timeline label is computed dynamically:\n"
        "- ``'1 year'`` when the dataset spans fewer than five years.\n"
        "- ``'5 years'`` otherwise.\n\n"
        "**Optional filter:**\n"
        "- `category_id` — restrict metrics to a single product category.\n\n"
        "Items within each window summary are sorted **descending** by "
        "`total_units_sold`."
    ),
    responses={
        200: {
            "description": "Successful purchase-history summary.",
        }
    },
)
async def get_purchase_history_summary(
    category_id: Optional[int] = Query(
        None,
        ge=1,
        description=(
            "Filter results to products belonging to a single category by its "
            "numeric ID.  When omitted, all categories are included."
        ),
        examples=[1],
    ),
    service: PurchaseHistoryService = Depends(get_purchase_history_service),
) -> PurchaseHistorySummaryResponse:
    """Return purchase-history aggregations for all standard time windows.

    Computes total units sold, average daily sales, and transaction-day counts
    for every product (subject to optional filters) across four time windows:
    1 month, 3 months, 6 months, and the full dataset timeline.

    Args:
        category_id: When provided, restrict metrics to products in this category.
        service: Injected :class:`PurchaseHistoryService` singleton.

    Returns:
        A :class:`PurchaseHistorySummaryResponse` containing dataset metadata
        and an ordered list of :class:`WindowSummary` objects — one per window.
    """
    dataset_meta = _build_dataset_metadata(service)
    first, last = service.get_dataset_date_range()
    full_days = (last - first).days + 1
    timeline_label = service.get_timeline_label()

    windows = []

    # Fixed rolling windows.
    for label, days in _WINDOW_CONFIGS:
        windows.append(
            _build_window_summary(
                service,
                label,
                days,
                category_id=category_id,
            )
        )

    # Full-dataset window.
    windows.append(
        _build_window_summary(
            service,
            timeline_label,
            full_days,
            category_id=category_id,
        )
    )

    return PurchaseHistorySummaryResponse(
        dataset=dataset_meta,
        windows=windows,
        applied_filters=_build_filter_description(category_id),
    )


# ============================================================================
# /top-products — top-N for a single window
# ============================================================================


@router.get(
    "/top-products",
    response_model=TopProductsResponse,
    summary="Top products by units sold for a specified time window",
    description=(
        "Returns the **top-N products** ranked by total units sold within a "
        "user-specified time window.  The window is anchored to the last date "
        "present in the dataset.\n\n"
        "**Window options** (`window` query parameter):\n"
        "- ``1m`` — last 1 month (30 days)\n"
        "- ``3m`` — last 3 months (90 days)\n"
        "- ``6m`` — last 6 months (180 days)\n"
        "- ``all`` — full dataset timeline (1 year or 5 years)\n\n"
        "**Optional filters:**\n"
        "- `category_id` — restrict to a single product category.\n"
        "- `limit` — number of top products to return (default 10, max 100)."
    ),
    responses={
        200: {"description": "Top-N products for the requested window."},
        422: {"description": "Invalid `window` parameter value."},
    },
)
async def get_top_products(
    window: _WindowParam = Query(
        "1m",
        description=(
            "Time window to rank products over.  "
            "One of: ``1m`` (30 days), ``3m`` (90 days), ``6m`` (180 days), "
            "``all`` (full dataset timeline)."
        ),
        examples=["1m"],
    ),
    limit: int = Query(
        _DEFAULT_LIMIT,
        ge=1,
        le=_MAX_LIMIT,
        description=f"Maximum number of top products to return (max {_MAX_LIMIT}).",
        examples=[10],
    ),
    category_id: Optional[int] = Query(
        None,
        ge=1,
        description=(
            "Filter to products in a single category by its numeric ID.  "
            "When omitted, all categories are included."
        ),
        examples=[1],
    ),
    service: PurchaseHistoryService = Depends(get_purchase_history_service),
) -> TopProductsResponse:
    """Return the top-N products by units sold for the requested time window.

    Args:
        window: One of ``"1m"``, ``"3m"``, ``"6m"``, ``"all"`` — selects the
            rolling time window to rank products over.
        limit: Number of top products to include in the response (1–100).
        category_id: When provided, restrict to products in this category.
        service: Injected :class:`PurchaseHistoryService` singleton.

    Returns:
        A :class:`TopProductsResponse` containing the ranked product list
        and window / filter metadata.
    """
    first, last = service.get_dataset_date_range()

    if window == "all":
        window_days = (last - first).days + 1
        window_label = service.get_timeline_label()
    else:
        window_days = _WINDOW_PARAM_MAP[window]
        window_label = {30: "1 month", 90: "3 months", 180: "6 months"}[window_days]

    window_start = last - timedelta(days=window_days - 1)

    raw = service.get_window_summary(
        window_days,
        category_id=category_id,
    )
    items = [PurchaseSummaryItem(**r) for r in raw[:limit]]

    return TopProductsResponse(
        window_label=window_label,
        window_days=window_days,
        window_start_date=window_start,
        window_end_date=last,
        limit=limit,
        items=items,
        applied_filters=_build_filter_description(category_id),
    )


# ============================================================================
# /categories/{category_id} and /locations/{location_id} specific endpoints
# ============================================================================


@router.get(
    "/categories/{category_id}/summary",
    response_model=PurchaseHistorySummaryResponse,
    summary="Category purchase history summary",
    description="Returns aggregated purchase metrics for all products in a specific category across all time windows.",
)
async def get_category_summary(
    category_id: int,
    service: PurchaseHistoryService = Depends(get_purchase_history_service),
) -> PurchaseHistorySummaryResponse:
    """Return aggregated purchase metrics for a specific category."""
    return await get_purchase_history_summary(
        category_id=category_id, service=service
    )


@router.get(
    "/categories/{category_id}/top-products",
    response_model=TopProductsResponse,
    summary="Top products for a specific category",
    description="Returns the top-N products for a specific category, ranked by units sold in a specified time window.",
)
async def get_category_top_products(
    category_id: int,
    window: _WindowParam = Query(
        "1m", description="Time window (e.g., 1m, 3m, 6m, all)."
    ),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    service: PurchaseHistoryService = Depends(get_purchase_history_service),
) -> TopProductsResponse:
    """Return the top-N products for a specific category."""
    return await get_top_products(
        window=window,
        limit=limit,
        category_id=category_id,
        service=service,
    )


# ============================================================================
# /product/{product_id} — per-product breakdown across all windows
# (dynamic route — MUST be declared AFTER all static paths above)
# ============================================================================


@router.get(
    "/product/{product_id}",
    response_model=ProductPurchaseHistoryResponse,
    summary="Purchase history breakdown for a single product",
    description=(
        "Returns a **per-product purchase-history breakdown** across all four "
        "standard time windows — 1 month, 3 months, 6 months, and the full "
        "dataset timeline.\n\n"
        "Each window entry includes:\n"
        "- `total_units_sold` — total units sold within the window.\n"
        "- `transaction_days` — days on which at least one unit was sold.\n"
        "- `avg_daily_sales` — average units sold per calendar day.\n"
        "- `total_receipts` — total units received (restocked) in the window.\n\n"
        "Returns HTTP 404 if no product with the given `product_id` exists "
        "in the product master."
    ),
    responses={
        404: {
            "description": "Product not found in the product master.",
            "content": {
                "application/json": {
                    "example": {"detail": "Product with id 99999 not found."}
                }
            },
        }
    },
)
async def get_product_purchase_history(
    product_id: int,
    service: PurchaseHistoryService = Depends(get_purchase_history_service),
) -> ProductPurchaseHistoryResponse:
    """Return a full purchase-history breakdown for a single product.

    Computes per-window aggregations (1 month, 3 months, 6 months, full
    dataset timeline) for the requested product SKU.

    Args:
        product_id: Numeric product/SKU identifier to look up.
        service: Injected :class:`PurchaseHistoryService` singleton.

    Returns:
        A :class:`ProductPurchaseHistoryResponse` with full window-by-window
        purchase metrics and dataset metadata.

    Raises:
        HTTPException: 404 if no product with ``product_id`` is found in
            the product master.
    """
    result = service.get_all_windows_for_product(
        product_id
    )

    pdata = result.get("product")
    if pdata is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product with id {product_id} not found.",
        )

    dataset_meta = _build_dataset_metadata(service)
    _, last = service.get_dataset_date_range()

    window_details: list[ProductWindowDetail] = []
    for w in result["windows"]:
        window_start = last - timedelta(days=w["window_days"] - 1)
        window_details.append(
            ProductWindowDetail(
                window_label=w["window_label"],
                window_days=w["window_days"],
                window_start_date=window_start,
                window_end_date=last,
                total_units_sold=w["total_units_sold"],
                transaction_days=w["transaction_days"],
                avg_daily_sales=w["avg_daily_sales"],
                total_receipts=w["total_receipts"],
            )
        )

    return ProductPurchaseHistoryResponse(
        sku_id=pdata["product_id"],
        product_code=pdata.get("product_code", ""),
        product_name=pdata.get("product_name", ""),
        category_id=pdata.get("category_id", 0),
        dataset=dataset_meta,
        windows=window_details,
    )
