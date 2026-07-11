"""Product data service with TTL-based in-memory caching.

This module provides a singleton service that loads product-related CSV data
(products, categories, seasonal patterns, velocity classes) into memory and
serves it with configurable cache expiration. Data is loaded lazily on first
access and automatically refreshed when the cache TTL expires.

Typical usage::

    from api.v1.services.product_data_service import get_product_data_service

    @router.get("/")
    async def list_products(service = Depends(get_product_data_service)):
        return service.get_products()
"""

from __future__ import annotations

import csv
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default CSV root relative to the project working directory.
_DEFAULT_CSV_DIR = Path("data/csv_exports/db2_csv_export")

# Cache time-to-live in seconds (10 minutes).
_CACHE_TTL_SECONDS = 600


def _read_csv(file_path: Path) -> List[Dict[str, str]]:
    """Read a CSV file and return a list of row dictionaries.

    Handles BOM-encoded files and normalises whitespace in header names
    and cell values.  Returns an empty list when the file is missing or
    unreadable so that callers always receive a safe iterable.

    Args:
        file_path: Absolute or relative path to the CSV file.

    Returns:
        A list of ``dict[str, str]`` — one dict per data row, keyed by
        the (stripped) column header.
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


def _safe_int(value: Optional[str]) -> int:
    """Parse a string to ``int``, returning ``0`` for empty/missing values."""
    if not value:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _safe_optional_int(value: Optional[str]) -> Optional[int]:
    """Parse a string to ``int``, returning ``None`` for NULL/empty values."""
    if not value or value.upper() == "NULL":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: Optional[str]) -> float:
    """Parse a string to ``float``, returning ``0.0`` for empty/missing values."""
    if not value or value.upper() == "NULL":
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _safe_bool(value: Optional[str]) -> bool:
    """Parse a CSV boolean flag (``"0"``/``"1"`` or ``"true"``/``"false"``)."""
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes")


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



class ProductDataService:
    """Thread-safe, TTL-cached service for product-domain CSV data.

    The service reads four CSV files from the ``db2_csv_export`` directory:

    * ``products.csv`` — 5 000 SKU master records.
    * ``product_categories.csv`` — 8 product categories.
    * ``seasonal_patterns.csv`` — 3 seasonal demand patterns.
    * ``velocity_classes.csv`` — 3 velocity classification tiers.

    Data is loaded lazily on first access and kept in memory.  Subsequent
    requests are served from cache until ``CACHE_TTL_SECONDS`` (default
    10 min) have elapsed, at which point the next request triggers a
    synchronous reload.

    This class is designed as a **singleton** — use
    :func:`get_product_data_service` as a FastAPI dependency.
    """

    def __init__(self, csv_dir: Path = _DEFAULT_CSV_DIR) -> None:
        self._csv_dir = csv_dir
        self._lock = threading.Lock()
        self._last_loaded: Optional[datetime] = None

        # Cached data stores.
        self._products: List[Dict[str, Any]] = []
        self._categories: List[Dict[str, Any]] = []
        self._seasonal_patterns: List[Dict[str, Any]] = []
        self._velocity_classes: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_products(self) -> List[Dict[str, Any]]:
        """Return the cached list of product records.

        Triggers a reload from disk when the cache is stale or empty.
        """
        self._refresh_if_stale()
        return self._products

    def get_product_categories(self) -> List[Dict[str, Any]]:
        """Return the cached list of product category records."""
        self._refresh_if_stale()
        return self._categories

    def get_seasonal_patterns(self) -> List[Dict[str, Any]]:
        """Return the cached list of seasonal pattern records."""
        self._refresh_if_stale()
        return self._seasonal_patterns

    def get_velocity_classes(self) -> List[Dict[str, Any]]:
        """Return the cached list of velocity class records."""
        self._refresh_if_stale()
        return self._velocity_classes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_if_stale(self) -> None:
        """Reload all CSV files if the cache has expired or is uninitialised.

        Uses a threading lock to prevent multiple concurrent reloads.
        """
        now = datetime.now(tz=timezone.utc)
        if (
            self._last_loaded is not None
            and (now - self._last_loaded).total_seconds() < _CACHE_TTL_SECONDS
        ):
            return  # Cache is still fresh.

        with self._lock:
            # Double-check after acquiring the lock (another thread may have
            # refreshed while we were waiting).
            if (
                self._last_loaded is not None
                and (
                    datetime.now(tz=timezone.utc) - self._last_loaded
                ).total_seconds()
                < _CACHE_TTL_SECONDS
            ):
                return

            logger.info("Refreshing product data cache from CSV files …")
            self._load_products()
            self._load_categories()
            self._load_seasonal_patterns()
            self._load_velocity_classes()
            self._last_loaded = datetime.now(tz=timezone.utc)
            logger.info(
                "Product data cache refreshed — %d products, %d categories, "
                "%d seasonal patterns, %d velocity classes.",
                len(self._products),
                len(self._categories),
                len(self._seasonal_patterns),
                len(self._velocity_classes),
            )

    # -- Individual loaders ------------------------------------------------

    def _load_products(self) -> None:
        """Parse ``products.csv`` capturing every column."""
        rows = _read_csv(self._csv_dir / "products.csv")
        parsed: List[Dict[str, Any]] = []
        for row in rows:
            try:
                pname = row.get("product_name", "")
                parsed.append(
                    {
                        "product_id": _safe_int(row.get("product_id")),
                        "product_code": row.get("product_code", ""),
                        "product_name": pname,
                        "category_id": _get_correct_category_id(pname),
                        "velocity_class_id": _safe_int(
                            row.get("velocity_class_id")
                        ),
                        "avg_retail_price": _safe_float(
                            row.get("avg_retail_price")
                        ),
                        "weight_lbs": _safe_float(row.get("weight_lbs")),
                        "shelf_life_days": _safe_optional_int(
                            row.get("shelf_life_days")
                        ),
                        "supplier_id": _safe_int(row.get("supplier_id")),
                    }
                )
            except Exception:
                logger.exception("Skipping malformed product row: %s", row)
        self._products = parsed

    def _load_categories(self) -> None:
        """Parse ``product_categories.csv`` capturing every column."""
        rows = _read_csv(self._csv_dir / "product_categories.csv")
        parsed: List[Dict[str, Any]] = []
        for row in rows:
            try:
                parsed.append(
                    {
                        "category_id": _safe_int(row.get("category_id")),
                        "category_code": row.get("category_code", ""),
                        "category_name": row.get("category_name", ""),
                        "avg_retail_price": _safe_float(
                            row.get("avg_retail_price")
                        ),
                        "shelf_life_days": _safe_optional_int(
                            row.get("shelf_life_days")
                        ),
                        "temperature_controlled": _safe_bool(
                            row.get("temperature_controlled")
                        ),
                        "hazmat_flag": _safe_bool(row.get("hazmat_flag")),
                        "typical_velocity": row.get("typical_velocity", ""),
                    }
                )
            except Exception:
                logger.exception("Skipping malformed category row: %s", row)
        self._categories = parsed

    def _load_seasonal_patterns(self) -> None:
        """Parse ``seasonal_patterns.csv`` capturing every column."""
        rows = _read_csv(self._csv_dir / "seasonal_patterns.csv")
        parsed: List[Dict[str, Any]] = []
        for row in rows:
            try:
                parsed.append(
                    {
                        "season_id": _safe_int(row.get("season_id")),
                        "season_name": row.get("season_name", ""),
                        "start_month": _safe_int(row.get("start_month")),
                        "end_month": _safe_int(row.get("end_month")),
                        "demand_multiplier": _safe_float(
                            row.get("demand_multiplier")
                        ),
                        "description": row.get("description", ""),
                    }
                )
            except Exception:
                logger.exception(
                    "Skipping malformed seasonal pattern row: %s", row
                )
        self._seasonal_patterns = parsed

    def _load_velocity_classes(self) -> None:
        """Parse ``velocity_classes.csv`` capturing every column."""
        rows = _read_csv(self._csv_dir / "velocity_classes.csv")
        parsed: List[Dict[str, Any]] = []
        for row in rows:
            try:
                parsed.append(
                    {
                        "velocity_class_id": _safe_int(
                            row.get("velocity_class_id")
                        ),
                        "velocity_code": row.get("velocity_code", ""),
                        "velocity_name": row.get("velocity_name", ""),
                        "annual_units_min": _safe_int(
                            row.get("annual_units_min")
                        ),
                        "annual_units_max": _safe_int(
                            row.get("annual_units_max")
                        ),
                        "description": row.get("description", ""),
                    }
                )
            except Exception:
                logger.exception(
                    "Skipping malformed velocity class row: %s", row
                )
        self._velocity_classes = parsed


# --------------------------------------------------------------------------
# Singleton instance & FastAPI dependency
# --------------------------------------------------------------------------

_service_instance: Optional[ProductDataService] = None
_instance_lock = threading.Lock()


def get_product_data_service() -> ProductDataService:
    """FastAPI dependency that returns the global ProductDataService singleton.

    Thread-safe lazy initialisation ensures only one instance is ever
    created, regardless of how many concurrent requests arrive.

    Returns:
        The shared :class:`ProductDataService` instance.
    """
    global _service_instance  # noqa: PLW0603
    if _service_instance is None:
        with _instance_lock:
            if _service_instance is None:
                _service_instance = ProductDataService()
    return _service_instance
