"""Purchase history data service with TTL-based in-memory caching.

This module provides a singleton service that loads inventory snapshot and
product CSV data into memory and exposes methods to compute purchase (sales)
aggregations across configurable rolling time windows.

The primary data source is ``inventory_daily_snapshots.csv`` (db5), which
records daily sales, receipts, and stock movements per SKU per location for
the full dataset period.  ``products.csv`` (db2) is joined in-memory to
supply product name, code, and category context.

Typical usage::

    from api.v1.services.purchase_history_service import (
        get_purchase_history_service,
    )

    @router.get("/summary")
    async def summary(service = Depends(get_purchase_history_service)):
        return service.get_window_summary(window_days=30)
"""

from __future__ import annotations

import csv
import logging
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSV source paths
# ---------------------------------------------------------------------------
_SNAPSHOTS_CSV = Path("data/csv_exports/db5_csv_export/inventory_daily_snapshots.csv")
_PRODUCTS_CSV = Path("data/csv_exports/db2_csv_export/products.csv")

# Cache TTL — 10 minutes.
_CACHE_TTL_SECONDS: int = 600

# Timeline thresholds (days).
_ONE_YEAR_DAYS: int = 365
_FIVE_YEAR_DAYS: int = 5 * 365


# ---------------------------------------------------------------------------
# Private helpers — CSV parsing
# ---------------------------------------------------------------------------


def _read_csv(file_path: Path) -> List[Dict[str, str]]:
    """Read a CSV file and return a list of row dicts.

    Handles BOM-encoded files and strips whitespace from headers and values.
    Returns an empty list when the file is missing or unreadable so callers
    always receive a safe iterable.

    Args:
        file_path: Absolute or relative path to the CSV file.

    Returns:
        A list of ``dict[str, str]`` — one dict per data row, keyed by the
        (stripped) column header.
    """
    if not file_path.exists():
        logger.warning("CSV file not found: %s", file_path)
        return []

    try:
        with file_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                logger.error("Empty or invalid CSV file: %s", file_path)
                return []

            rows: List[Dict[str, str]] = []
            for row in reader:
                normalised = {
                    key.strip().lstrip("\ufeff"): (value or "").strip()
                    for key, value in row.items()
                }
                rows.append(normalised)

            logger.info("Loaded %d rows from %s", len(rows), file_path.name)
            return rows
    except Exception:
        logger.exception("Error reading CSV file %s", file_path)
        return []


def _safe_int(value: Optional[str], default: int = 0) -> int:
    """Parse a string to ``int``, returning *default* for empty/invalid values."""
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_date(value: Optional[str]) -> Optional[date]:
    """Parse an ISO-8601 date string (``YYYY-MM-DD``) to a :class:`date`.

    Returns ``None`` when the value is absent or unparseable.

    Args:
        value: Raw string from the CSV cell.

    Returns:
        A :class:`datetime.date` instance, or ``None`` on failure.
    """
    if not value:
        return None
    try:
        # Truncate any time component before parsing.
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _get_correct_category_id(product_name: str) -> int:
    """Determine correct category_id based on semantic product name."""
    name = product_name.lower()
    
    # 1. Electronics
    if any(k in name for k in [
        "toaster", "smartphone", "earbuds", "keyboard", "blender", "vacuum",
        "controller", "mouse", "webcam", "laptop", "toothbrush electric",
        "tablet", "clock digital", "smart watch", "speaker", "coffee maker",
        "monitor", "power bank", "cable"
    ]):
        return 1
        
    # 2. Apparel
    if any(k in name for k in [
        "shorts", "dress", "jacket", "socks", "t-shirt", "polo", "jeans",
        "gloves", "cap", "hoodie", "scarf", "shoes"
    ]):
        return 2
        
    # 3. Home Goods
    if any(k in name for k in [
        "pillow", "mirror", "lamp", "pot ceramic", "rug", "bedding", "curtains", "ice melt", "water bottle"
    ]):
        return 3
        
    # 4. Sporting Goods
    if any(k in name for k in [
        "skateboard", "racket", "glove", "shovel", "ball", "dumbbells",
        "mat", "goggles", "hiking", "tent", "bicycle"
    ]):
        return 4
        
    # 5. Toys
    if any(k in name for k in [
        "yo-yo", "board game", "doll", "lego", "plush", "card pack",
        "blocks", "figure", "toy car", "kite", "puzzle"
    ]):
        return 5
        
    # 6. Health & Beauty
    if any(k in name for k in [
        "mask", "deodorant", "vitamins", "sunscreen", "perfume", "lip balm",
        "shampoo", "eye cream", "serum", "moisturizer", "cologne"
    ]):
        return 6
        
    # 7. Grocery
    if any(k in name for k in [
        "milk", "rice", "beans", "olive oil", "butter", "peanut", "yogurt",
        "bread", "eggs", "cheese", "granola", "pasta"
    ]):
        return 7
        
    # 8. Seasonal
    if any(k in name for k in [
        "ornament", "pumpkin", "chocolate", "centerpiece", "fireworks",
        "tree", "decoration", "basket", "costume"
    ]):
        return 8
        
    return 1 # Fallback



# ---------------------------------------------------------------------------
# SnapshotRecord — lightweight typed container
# ---------------------------------------------------------------------------


class _SnapshotRecord:
    """Lightweight container for a single ``inventory_daily_snapshots`` row.

    Attributes:
        snapshot_date: The calendar date of the snapshot.
        sku_id: Product SKU identifier.
        location_id: Location identifier.
        sales: Units sold on this day (always >= 0).
        receipts: Units received on this day.
        closing_stock: Closing inventory level at end of day.
    """

    __slots__ = (
        "snapshot_date",
        "sku_id",
        "location_id",
        "sales",
        "receipts",
        "closing_stock",
    )

    def __init__(
        self,
        snapshot_date: date,
        sku_id: int,
        location_id: int,
        sales: int,
        receipts: int,
        closing_stock: int,
    ) -> None:
        self.snapshot_date = snapshot_date
        self.sku_id = sku_id
        self.location_id = location_id
        self.sales = sales
        self.receipts = receipts
        self.closing_stock = closing_stock


# ---------------------------------------------------------------------------
# PurchaseHistoryService
# ---------------------------------------------------------------------------


class PurchaseHistoryService:
    """Thread-safe, TTL-cached service for purchase-history analytics.

    Loads two CSV data sources:

    * ``inventory_daily_snapshots.csv`` (db5) — daily sales per SKU/location.
    * ``products.csv`` (db2) — SKU master for product name/code/category joins.

    Data is loaded lazily on first access and kept in memory.  Subsequent
    requests are served from cache until ``_CACHE_TTL_SECONDS`` (10 min) have
    elapsed, at which point the next request triggers a synchronous reload.

    This class is designed as a **singleton** — use
    :func:`get_purchase_history_service` as a FastAPI dependency.
    """

    def __init__(
        self,
        snapshots_csv: Path = _SNAPSHOTS_CSV,
        products_csv: Path = _PRODUCTS_CSV,
    ) -> None:
        self._snapshots_csv = snapshots_csv
        self._products_csv = products_csv
        self._lock = threading.Lock()
        self._last_loaded: Optional[datetime] = None

        # Cached data stores.
        self._snapshots: List[_SnapshotRecord] = []
        # product_id → {product_name, product_code, category_id, ...}
        self._products: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_dataset_date_range(self) -> Tuple[date, date]:
        """Return the (min_date, max_date) present in the snapshot dataset.

        Returns:
            A tuple ``(first_date, last_date)`` of :class:`datetime.date`.
            Falls back to today's date for both values if the dataset is empty.
        """
        self._refresh_if_stale()
        if not self._snapshots:
            today = date.today()
            return (today, today)
        dates = [r.snapshot_date for r in self._snapshots]
        return (min(dates), max(dates))

    def get_timeline_label(self) -> str:
        """Derive a human-readable timeline label from the dataset span.

        If the gap between the earliest and latest snapshot is less than
        :const:`_ONE_YEAR_DAYS` the label is ``"1 year"``.  Otherwise it
        is ``"5 years"``.

        Returns:
            One of ``"1 year"`` or ``"5 years"``.
        """
        first, last = self.get_dataset_date_range()
        span_days = (last - first).days
        return "1 year" if span_days < _FIVE_YEAR_DAYS else "5 years"

    def get_window_summary(
        self,
        window_days: int,
        *,
        product_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Aggregate total units sold per product over a rolling time window.

        The window is anchored to the **last date present in the dataset**
        rather than today, so results are always consistent with the available
        data.

        Args:
            window_days: Number of calendar days to look back from the last
                dataset date (e.g. ``30`` for 1 month, ``90`` for 3 months).
            product_id: When provided, restrict results to this single product.
            category_id: When provided, restrict to products in this category.

        Returns:
            A list of dicts, each representing one product with keys:

            * ``sku_id`` — product identifier.
            * ``product_code`` — human-readable code (e.g. ``"ELEC-1001"``).
            * ``product_name`` — descriptive product name.
            * ``category_id`` — product category foreign key.
            * ``total_units_sold`` — total units sold in the window.
            * ``transaction_days`` — number of distinct days with sales > 0.
            * ``avg_daily_sales`` — average units sold per calendar day in the window.
            * ``total_receipts`` — total units received in the window.

            Results are sorted descending by ``total_units_sold``.
        """
        self._refresh_if_stale()
        _, last_date = self.get_dataset_date_range()
        window_start = last_date - timedelta(days=window_days - 1)

        # Filter snapshots inside the window.
        rows = [
            r
            for r in self._snapshots
            if r.snapshot_date >= window_start and r.snapshot_date <= last_date
        ]

        if product_id is not None:
            rows = [r for r in rows if r.sku_id == product_id]
        if category_id is not None:
            allowed_skus = {
                pid
                for pid, pdata in self._products.items()
                if pdata.get("category_id") == category_id
            }
            rows = [r for r in rows if r.sku_id in allowed_skus]

        # Aggregate per SKU.
        totals: Dict[int, Dict[str, Any]] = defaultdict(
            lambda: {
                "total_units_sold": 0,
                "transaction_days": 0,
                "total_receipts": 0,
            }
        )
        for r in rows:
            agg = totals[r.sku_id]
            agg["total_units_sold"] += r.sales
            agg["total_receipts"] += r.receipts
            if r.sales > 0:
                agg["transaction_days"] += 1

        result: List[Dict[str, Any]] = []
        for sku_id, agg in totals.items():
            pdata = self._products.get(sku_id, {})
            avg_daily = (
                round(agg["total_units_sold"] / window_days, 2)
                if window_days > 0
                else 0.0
            )
            result.append(
                {
                    "sku_id": sku_id,
                    "product_code": pdata.get("product_code", ""),
                    "product_name": pdata.get("product_name", ""),
                    "category_id": pdata.get("category_id", 0),
                    "total_units_sold": agg["total_units_sold"],
                    "transaction_days": agg["transaction_days"],
                    "avg_daily_sales": avg_daily,
                    "total_receipts": agg["total_receipts"],
                }
            )

        result.sort(key=lambda x: x["total_units_sold"], reverse=True)
        return result

    def get_all_windows_for_product(
        self,
        product_id: int,
    ) -> Dict[str, Any]:
        """Return purchase metrics for a single product across all windows.

        Computes summaries for the 1-month, 3-month, 6-month, and full-dataset
        windows simultaneously for a specific product.

        Args:
            product_id: The numeric SKU / product ID to analyse.

        Returns:
            A dict with keys ``"product"`` (product metadata) and
            ``"windows"`` (a list of per-window summary dicts, each including
            the ``window_label``, ``window_days``, and aggregated metrics).
            Returns ``None`` for the ``"product"`` key if the SKU is unknown.
        """
        self._refresh_if_stale()
        pdata = self._products.get(product_id)

        windows = []
        for label, days in [
            ("1 month", 30),
            ("3 months", 90),
            ("6 months", 180),
        ]:
            summaries = self.get_window_summary(
                days,
                product_id=product_id,
            )
            agg = summaries[0] if summaries else None
            windows.append(
                {
                    "window_label": label,
                    "window_days": days,
                    "total_units_sold": agg["total_units_sold"] if agg else 0,
                    "transaction_days": agg["transaction_days"] if agg else 0,
                    "avg_daily_sales": agg["avg_daily_sales"] if agg else 0.0,
                    "total_receipts": agg["total_receipts"] if agg else 0,
                }
            )

        # Full-dataset window.
        first, last = self.get_dataset_date_range()
        full_days = (last - first).days + 1
        full_summaries = self.get_window_summary(
            full_days,
            product_id=product_id,
        )
        full_agg = full_summaries[0] if full_summaries else None
        windows.append(
            {
                "window_label": self.get_timeline_label(),
                "window_days": full_days,
                "total_units_sold": full_agg["total_units_sold"] if full_agg else 0,
                "transaction_days": full_agg["transaction_days"] if full_agg else 0,
                "avg_daily_sales": full_agg["avg_daily_sales"] if full_agg else 0.0,
                "total_receipts": full_agg["total_receipts"] if full_agg else 0,
            }
        )

        return {
            "product": pdata,
            "windows": windows,
        }

    # ------------------------------------------------------------------
    # Internal helpers — cache management
    # ------------------------------------------------------------------

    def _refresh_if_stale(self) -> None:
        """Reload all CSV files if the cache has expired or is uninitialised.

        Uses a double-checked locking pattern to avoid redundant reloads when
        multiple threads arrive simultaneously after cache expiry.
        """
        now = datetime.now(tz=timezone.utc)
        if (
            self._last_loaded is not None
            and (now - self._last_loaded).total_seconds() < _CACHE_TTL_SECONDS
        ):
            return  # Cache is still fresh.

        with self._lock:
            # Re-check inside the lock — another thread may have refreshed
            # while we were waiting to acquire.
            if (
                self._last_loaded is not None
                and (
                    datetime.now(tz=timezone.utc) - self._last_loaded
                ).total_seconds()
                < _CACHE_TTL_SECONDS
            ):
                return

            logger.info("Refreshing purchase history cache from CSV files …")
            self._load_products()
            self._load_snapshots()
            self._last_loaded = datetime.now(tz=timezone.utc)
            logger.info(
                "Purchase history cache refreshed — %d snapshot rows, "
                "%d products.",
                len(self._snapshots),
                len(self._products),
            )

    # -- Individual loaders ------------------------------------------------

    def _load_products(self) -> None:
        """Parse ``products.csv`` into a sku_id-keyed lookup dict.

        .. note::
            The inventory snapshot dataset (db5) stores ``sku_id`` as
            ``product_id + 10000`` (e.g. product_id=1 → sku_id=10001).
            We key the lookup dict by ``product_id + 10000`` so that
            :meth:`get_window_summary` can resolve product metadata
            directly from the snapshot ``sku_id`` without any adjustment.
        """
        rows = _read_csv(self._products_csv)
        parsed: Dict[int, Dict[str, Any]] = {}
        _SKU_OFFSET = 10000  # snapshot sku_id = product_id + _SKU_OFFSET
        for row in rows:
            try:
                pid = _safe_int(row.get("product_id"))
                if pid == 0:
                    continue
                sku_id = pid + _SKU_OFFSET
                pname = row.get("product_name", "")
                parsed[sku_id] = {
                    "product_id": pid,
                    "product_code": row.get("product_code", ""),
                    "product_name": pname,
                    "category_id": _get_correct_category_id(pname),
                    "supplier_id": _safe_int(row.get("supplier_id")),
                }
            except Exception:
                logger.exception("Skipping malformed product row: %s", row)
        self._products = parsed

    def _load_snapshots(self) -> None:
        """Parse ``inventory_daily_snapshots.csv`` into typed records."""
        rows = _read_csv(self._snapshots_csv)
        parsed: List[_SnapshotRecord] = []
        for row in rows:
            try:
                snap_date = _safe_date(row.get("snapshot_date"))
                if snap_date is None:
                    continue
                parsed.append(
                    _SnapshotRecord(
                        snapshot_date=snap_date,
                        sku_id=_safe_int(row.get("sku_id")),
                        location_id=_safe_int(row.get("location_id")),
                        sales=max(0, _safe_int(row.get("sales"))),
                        receipts=max(0, _safe_int(row.get("receipts"))),
                        closing_stock=_safe_int(row.get("closing_stock")),
                    )
                )
            except Exception:
                logger.exception("Skipping malformed snapshot row: %s", row)
        self._snapshots = parsed


# ---------------------------------------------------------------------------
# Singleton instance & FastAPI dependency
# ---------------------------------------------------------------------------

_service_instance: Optional[PurchaseHistoryService] = None
_instance_lock = threading.Lock()


def get_purchase_history_service() -> PurchaseHistoryService:
    """FastAPI dependency returning the global :class:`PurchaseHistoryService` singleton.

    Thread-safe lazy initialisation ensures only one instance is ever created,
    regardless of how many concurrent requests arrive.

    Returns:
        The shared :class:`PurchaseHistoryService` instance.
    """
    global _service_instance  # noqa: PLW0603
    if _service_instance is None:
        with _instance_lock:
            if _service_instance is None:
                _service_instance = PurchaseHistoryService()
    return _service_instance
