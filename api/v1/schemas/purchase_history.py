"""Pydantic response schemas for purchase-history analytics API endpoints.

This module defines the data contracts for all resources served by the
``/purchase-history`` router:

* :class:`DatasetMetadata` — dataset date range and derived timeline label.
* :class:`PurchaseSummaryItem` — per-product aggregated metrics for one window.
* :class:`WindowSummary` — one time-window result (label + list of items).
* :class:`PurchaseHistorySummaryResponse` — full multi-window summary response.
* :class:`ProductWindowDetail` — single-window detail used inside a per-product breakdown.
* :class:`ProductPurchaseHistoryResponse` — full per-product, multi-window breakdown.
* :class:`TopProductsResponse` — top-N products for a single window.

All schemas derive from :class:`pydantic.BaseModel` with ``from_attributes``
enabled so they can be constructed from ORM-style objects *or* plain dicts.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Dataset Metadata
# ---------------------------------------------------------------------------


class DatasetMetadata(BaseModel):
    """Metadata describing the temporal extent of the inventory snapshot dataset.

    Attributes:
        first_date: The earliest snapshot date present in the dataset.
        last_date: The latest snapshot date present in the dataset.
        timeline_label: Human-readable label for the full dataset span —
            either ``"1 year"`` (span < 5 years) or ``"5 years"``.
        total_snapshot_days: Total number of calendar days between
            ``first_date`` and ``last_date`` inclusive.
    """

    model_config = ConfigDict(from_attributes=True)

    first_date: date = Field(
        ...,
        description="The earliest snapshot date present in the dataset.",
        examples=["2026-01-01"],
    )
    last_date: date = Field(
        ...,
        description="The latest snapshot date present in the dataset.",
        examples=["2026-12-28"],
    )
    timeline_label: str = Field(
        ...,
        description=(
            "Human-readable label for the full dataset time span. "
            "Either '1 year' (< 5 years of data) or '5 years'."
        ),
        examples=["1 year"],
    )
    total_snapshot_days: int = Field(
        ...,
        description="Total calendar days between first_date and last_date, inclusive.",
        examples=[362],
    )


# ---------------------------------------------------------------------------
# Purchase Summary Item
# ---------------------------------------------------------------------------


class PurchaseSummaryItem(BaseModel):
    """Aggregated purchase metrics for a single product within a time window.

    Attributes:
        sku_id: Product SKU / product identifier.
        product_code: Human-readable SKU code (e.g. ``"ELEC-1001"``).
        product_name: Descriptive product name.
        category_id: Foreign key to the product category.
        total_units_sold: Total units sold during the time window.
        transaction_days: Number of distinct days on which units were sold.
        avg_daily_sales: Average units sold per calendar day within the window.
        total_receipts: Total units received (restocked) during the window.
    """

    model_config = ConfigDict(from_attributes=True)

    sku_id: int = Field(
        ...,
        description="Product SKU / unique product identifier.",
        examples=[10713],
    )
    product_code: str = Field(
        ...,
        description="Human-readable SKU code.",
        examples=["ELEC-1001"],
    )
    product_name: str = Field(
        ...,
        description="Descriptive product name.",
        examples=["Toaster 4-Slice v1"],
    )
    category_id: int = Field(
        ...,
        description="Foreign key to the product category.",
        examples=[1],
    )
    total_units_sold: int = Field(
        ...,
        description="Total units sold during the time window.",
        examples=[450],
    )
    transaction_days: int = Field(
        ...,
        description="Number of distinct days on which at least one unit was sold.",
        examples=[28],
    )
    avg_daily_sales: float = Field(
        ...,
        description="Average units sold per calendar day within the window.",
        examples=[15.0],
    )
    total_receipts: int = Field(
        ...,
        description="Total units received (restocked) during the window.",
        examples=[200],
    )


# ---------------------------------------------------------------------------
# Window Summary
# ---------------------------------------------------------------------------


class WindowSummary(BaseModel):
    """Aggregated purchase data for one time window across all (filtered) products.

    Attributes:
        window_label: Human-readable label for the window
            (e.g. ``"1 month"``, ``"3 months"``, ``"6 months"``, ``"1 year"``).
        window_days: Number of calendar days in the window.
        window_start_date: The inclusive start date of this window, anchored to
            the last date present in the dataset.
        window_end_date: The inclusive end date (= last dataset date).
        total_products_with_sales: Count of distinct products that had at
            least one sale within the window.
        grand_total_units_sold: Sum of all units sold across all products
            within the window.
        items: Per-product purchase summaries, sorted descending by
            ``total_units_sold``.
    """

    model_config = ConfigDict(from_attributes=True)

    window_label: str = Field(
        ...,
        description=(
            "Human-readable time-window label "
            "(e.g. '1 month', '3 months', '6 months', '1 year')."
        ),
        examples=["1 month"],
    )
    window_days: int = Field(
        ...,
        description="Number of calendar days in the window.",
        examples=[30],
    )
    window_start_date: date = Field(
        ...,
        description="Inclusive start date of the window.",
        examples=["2026-11-28"],
    )
    window_end_date: date = Field(
        ...,
        description="Inclusive end date of the window (= last dataset date).",
        examples=["2026-12-28"],
    )
    total_products_with_sales: int = Field(
        ...,
        description="Count of distinct products with at least one sale in the window.",
        examples=[120],
    )
    grand_total_units_sold: int = Field(
        ...,
        description="Sum of all units sold across all products within the window.",
        examples=[54320],
    )
    items: List[PurchaseSummaryItem] = Field(
        ...,
        description=(
            "Per-product purchase summaries sorted descending by total_units_sold."
        ),
    )


# ---------------------------------------------------------------------------
# Full Summary Response (all windows)
# ---------------------------------------------------------------------------


class PurchaseHistorySummaryResponse(BaseModel):
    """Full multi-window purchase-history summary response.

    Returns aggregated sales data for all four standard time windows —
    1 month, 3 months, 6 months, and the full dataset timeline — in a single
    response payload, together with dataset metadata for context.

    Attributes:
        dataset: Metadata about the inventory snapshot dataset.
        windows: Ordered list of :class:`WindowSummary` objects — one per
            time window (1 month → 3 months → 6 months → full timeline).
        applied_filters: Human-readable description of any filters applied
            to the query (``None`` when no filters were used).
    """

    model_config = ConfigDict(from_attributes=True)

    dataset: DatasetMetadata = Field(
        ...,
        description="Metadata about the inventory snapshot dataset used for analysis.",
    )
    windows: List[WindowSummary] = Field(
        ...,
        description=(
            "Ordered list of window summaries: 1 month, 3 months, 6 months, "
            "and full dataset timeline."
        ),
    )
    applied_filters: Optional[str] = Field(
        None,
        description=(
            "Human-readable summary of query filters applied "
            "(None when no filters were used)."
        ),
        examples=["location_id=5, category_id=1"],
    )


# ---------------------------------------------------------------------------
# Per-product window detail
# ---------------------------------------------------------------------------


class ProductWindowDetail(BaseModel):
    """Purchase metrics for a single product within one specific time window.

    Used within :class:`ProductPurchaseHistoryResponse` to present a breakdown
    by time window for a single product.

    Attributes:
        window_label: Human-readable label for the window.
        window_days: Number of calendar days in the window.
        window_start_date: Inclusive start date of the window.
        window_end_date: Inclusive end date (= last dataset date).
        total_units_sold: Total units sold in the window.
        transaction_days: Days with at least one sale.
        avg_daily_sales: Average units sold per calendar day.
        total_receipts: Total units received in the window.
    """

    model_config = ConfigDict(from_attributes=True)

    window_label: str = Field(
        ...,
        description="Human-readable time-window label.",
        examples=["3 months"],
    )
    window_days: int = Field(
        ...,
        description="Number of calendar days in the window.",
        examples=[90],
    )
    window_start_date: date = Field(
        ...,
        description="Inclusive start date of the window.",
        examples=["2026-09-29"],
    )
    window_end_date: date = Field(
        ...,
        description="Inclusive end date of the window (= last dataset date).",
        examples=["2026-12-28"],
    )
    total_units_sold: int = Field(
        ...,
        description="Total units sold by this product in the window.",
        examples=[135],
    )
    transaction_days: int = Field(
        ...,
        description="Number of days with at least one unit sold.",
        examples=[72],
    )
    avg_daily_sales: float = Field(
        ...,
        description="Average units sold per calendar day within the window.",
        examples=[1.5],
    )
    total_receipts: int = Field(
        ...,
        description="Total units received by this product in the window.",
        examples=[60],
    )


# ---------------------------------------------------------------------------
# Per-product full-history response
# ---------------------------------------------------------------------------


class ProductPurchaseHistoryResponse(BaseModel):
    """Full purchase-history breakdown for a single product across all windows.

    Attributes:
        sku_id: Product SKU / unique product identifier.
        product_code: Human-readable SKU code.
        product_name: Descriptive product name.
        category_id: Product category foreign key.
        dataset: Metadata about the inventory snapshot dataset.
        windows: List of per-window metrics covering 1 month, 3 months,
            6 months, and the full dataset timeline.
        applied_location_id: Location filter applied to the query, if any.
    """

    model_config = ConfigDict(from_attributes=True)

    sku_id: int = Field(
        ...,
        description="Product SKU / unique product identifier.",
        examples=[10713],
    )
    product_code: str = Field(
        ...,
        description="Human-readable SKU code.",
        examples=["ELEC-1001"],
    )
    product_name: str = Field(
        ...,
        description="Descriptive product name.",
        examples=["Toaster 4-Slice v1"],
    )
    category_id: int = Field(
        ...,
        description="Foreign key to the product category.",
        examples=[1],
    )
    dataset: DatasetMetadata = Field(
        ...,
        description="Metadata about the inventory snapshot dataset.",
    )
    windows: List[ProductWindowDetail] = Field(
        ...,
        description=(
            "Per-window metrics: 1 month, 3 months, 6 months, "
            "and full dataset timeline."
        ),
    )
    applied_location_id: Optional[int] = Field(
        None,
        description="Location ID filter applied to the query, if any.",
        examples=[5],
    )


# ---------------------------------------------------------------------------
# Top-products response
# ---------------------------------------------------------------------------


class TopProductsResponse(BaseModel):
    """Top-N products ranked by units sold within a specific time window.

    Attributes:
        window_label: Human-readable label for the requested window.
        window_days: Number of calendar days in the window.
        window_start_date: Inclusive start date of the window.
        window_end_date: Inclusive end date (= last dataset date).
        limit: Maximum number of products returned.
        items: Ranked list of products (descending by total_units_sold).
        applied_filters: Human-readable description of applied filters, if any.
    """

    model_config = ConfigDict(from_attributes=True)

    window_label: str = Field(
        ...,
        description="Human-readable label for the requested time window.",
        examples=["1 month"],
    )
    window_days: int = Field(
        ...,
        description="Number of calendar days in the window.",
        examples=[30],
    )
    window_start_date: date = Field(
        ...,
        description="Inclusive start date of the window.",
        examples=["2026-11-28"],
    )
    window_end_date: date = Field(
        ...,
        description="Inclusive end date of the window.",
        examples=["2026-12-28"],
    )
    limit: int = Field(
        ...,
        description="Maximum number of products in the ranking.",
        examples=[10],
    )
    items: List[PurchaseSummaryItem] = Field(
        ...,
        description="Top-N products sorted descending by total_units_sold.",
    )
    applied_filters: Optional[str] = Field(
        None,
        description="Human-readable description of applied filters, if any.",
        examples=["category_id=1"],
    )
