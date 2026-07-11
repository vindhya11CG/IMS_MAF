"""Products API router — CRUD-style read endpoints for product-domain data.

Exposes paginated and non-paginated ``GET`` endpoints for four resources
sourced from DB2 CSV exports:

* **Products** (``/``, ``/{product_id}``) — 5 000 SKU master records with
  pagination support.
* **Product Categories** (``/categories``, ``/categories/{category_id}``) —
  8 reference records.
* **Seasonal Patterns** (``/seasonal-patterns``,
  ``/seasonal-patterns/{season_id}``) — 3 demand multiplier records.
* **Velocity Classes** (``/velocity-classes``,
  ``/velocity-classes/{velocity_class_id}``) — 3 classification tiers.

All data is served from an in-memory cache (:class:`ProductDataService`)
that lazily loads CSV files on first access and refreshes every 10 minutes.

.. note::
    Static sub-resource routes (``/categories``, ``/seasonal-patterns``,
    ``/velocity-classes``) are declared **before** the dynamic
    ``/{product_id}`` route to prevent FastAPI from interpreting path
    segments like ``"categories"`` as an integer ``product_id``.
"""

from __future__ import annotations

import math
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.v1.schemas.products import (
    PaginatedProductResponse,
    ProductCategoryResponse,
    ProductResponse,
    SeasonalPatternResponse,
    VelocityClassResponse,
)
from api.v1.services.product_data_service import (
    ProductDataService,
    get_product_data_service,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Default pagination constants
# ---------------------------------------------------------------------------
_DEFAULT_PAGE = 1
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


# ============================================================================
# Products — List (paginated)
# ============================================================================


@router.get(
    "/",
    response_model=PaginatedProductResponse,
    summary="List all products (paginated)",
    description=(
        "Returns a paginated list of all products from the product master "
        "catalogue.  Each record contains the full set of SKU attributes "
        "including product code, category, velocity class, pricing, weight, "
        "shelf life, and primary supplier.\n\n"
        "**Pagination:** Use the `page` and `page_size` query parameters to "
        "navigate through the result set.  The response includes `total`, "
        "`total_pages`, and the current `page` for client-side paging controls."
    ),
)
async def list_products(
    page: int = Query(
        _DEFAULT_PAGE,
        ge=1,
        description="1-indexed page number.",
    ),
    page_size: int = Query(
        _DEFAULT_PAGE_SIZE,
        ge=1,
        le=_MAX_PAGE_SIZE,
        description=f"Number of items per page (max {_MAX_PAGE_SIZE}).",
    ),
    service: ProductDataService = Depends(get_product_data_service),
) -> PaginatedProductResponse:
    """Return a paginated page of product records.

    Args:
        page: 1-indexed page number (default 1).
        page_size: Items per page, clamped to ``[1, 200]`` (default 50).
        service: Injected :class:`ProductDataService` singleton.

    Returns:
        A :class:`PaginatedProductResponse` containing the requested page
        of :class:`ProductResponse` items together with pagination metadata.
    """
    all_products = service.get_products()
    total = len(all_products)
    total_pages = max(1, math.ceil(total / page_size))

    start = (page - 1) * page_size
    end = start + page_size
    page_items = all_products[start:end]

    return PaginatedProductResponse(
        items=[ProductResponse(**item) for item in page_items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ============================================================================
# Product Categories  (static paths — MUST be before /{product_id})
# ============================================================================


@router.get(
    "/categories",
    response_model=List[ProductCategoryResponse],
    summary="List all product categories",
    description=(
        "Returns the complete list of product categories.  Each category "
        "record includes the category code, name, average retail price, "
        "shelf life, temperature-control and hazmat flags, and the typical "
        "velocity classification."
    ),
)
async def list_product_categories(
    service: ProductDataService = Depends(get_product_data_service),
) -> List[ProductCategoryResponse]:
    """Return all product categories.

    Args:
        service: Injected :class:`ProductDataService` singleton.

    Returns:
        A list of :class:`ProductCategoryResponse` records.
    """
    return [
        ProductCategoryResponse(**cat)
        for cat in service.get_product_categories()
    ]


@router.get(
    "/categories/{category_id}",
    response_model=ProductCategoryResponse,
    summary="Get a product category by ID",
    description=(
        "Returns a single product category identified by its unique "
        "``category_id``.  Returns HTTP 404 if no category with the given "
        "ID exists."
    ),
    responses={
        404: {
            "description": "Category not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Product category with id 99 not found."}
                }
            },
        }
    },
)
async def get_product_category(
    category_id: int,
    service: ProductDataService = Depends(get_product_data_service),
) -> ProductCategoryResponse:
    """Return a single product category by its unique identifier.

    Args:
        category_id: The numeric category ID to look up.
        service: Injected :class:`ProductDataService` singleton.

    Returns:
        A :class:`ProductCategoryResponse` for the matching category.

    Raises:
        HTTPException: 404 if no category with ``category_id`` exists.
    """
    for cat in service.get_product_categories():
        if cat["category_id"] == category_id:
            return ProductCategoryResponse(**cat)

    raise HTTPException(
        status_code=404,
        detail=f"Product category with id {category_id} not found.",
    )


# ============================================================================
# Seasonal Patterns  (static paths — MUST be before /{product_id})
# ============================================================================


@router.get(
    "/seasonal-patterns",
    response_model=List[SeasonalPatternResponse],
    summary="List all seasonal patterns",
    description=(
        "Returns the complete list of seasonal demand patterns used for "
        "demand forecasting.  Each record defines a time window "
        "(``start_month`` to ``end_month``) and a ``demand_multiplier`` "
        "applied to baseline demand during that period."
    ),
)
async def list_seasonal_patterns(
    service: ProductDataService = Depends(get_product_data_service),
) -> List[SeasonalPatternResponse]:
    """Return all seasonal demand pattern records.

    Args:
        service: Injected :class:`ProductDataService` singleton.

    Returns:
        A list of :class:`SeasonalPatternResponse` records.
    """
    return [
        SeasonalPatternResponse(**sp)
        for sp in service.get_seasonal_patterns()
    ]


@router.get(
    "/seasonal-patterns/{season_id}",
    response_model=SeasonalPatternResponse,
    summary="Get a seasonal pattern by ID",
    description=(
        "Returns a single seasonal demand pattern identified by its unique "
        "``season_id``.  Returns HTTP 404 if no pattern with the given ID "
        "exists."
    ),
    responses={
        404: {
            "description": "Seasonal pattern not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Seasonal pattern with id 99 not found."
                    }
                }
            },
        }
    },
)
async def get_seasonal_pattern(
    season_id: int,
    service: ProductDataService = Depends(get_product_data_service),
) -> SeasonalPatternResponse:
    """Return a single seasonal pattern by its unique identifier.

    Args:
        season_id: The numeric season ID to look up.
        service: Injected :class:`ProductDataService` singleton.

    Returns:
        A :class:`SeasonalPatternResponse` for the matching pattern.

    Raises:
        HTTPException: 404 if no pattern with ``season_id`` exists.
    """
    for sp in service.get_seasonal_patterns():
        if sp["season_id"] == season_id:
            return SeasonalPatternResponse(**sp)

    raise HTTPException(
        status_code=404,
        detail=f"Seasonal pattern with id {season_id} not found.",
    )


# ============================================================================
# Velocity Classes  (static paths — MUST be before /{product_id})
# ============================================================================


@router.get(
    "/velocity-classes",
    response_model=List[VelocityClassResponse],
    summary="List all velocity classes",
    description=(
        "Returns the complete list of product velocity classification tiers.  "
        "Velocity classes categorise SKUs by annual unit throughput into "
        "tiers such as High (A), Medium (B), and Low (C) velocity."
    ),
)
async def list_velocity_classes(
    service: ProductDataService = Depends(get_product_data_service),
) -> List[VelocityClassResponse]:
    """Return all velocity classification records.

    Args:
        service: Injected :class:`ProductDataService` singleton.

    Returns:
        A list of :class:`VelocityClassResponse` records.
    """
    return [
        VelocityClassResponse(**vc)
        for vc in service.get_velocity_classes()
    ]


@router.get(
    "/velocity-classes/{velocity_class_id}",
    response_model=VelocityClassResponse,
    summary="Get a velocity class by ID",
    description=(
        "Returns a single velocity class identified by its unique "
        "``velocity_class_id``.  Returns HTTP 404 if no class with the "
        "given ID exists."
    ),
    responses={
        404: {
            "description": "Velocity class not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Velocity class with id 99 not found."
                    }
                }
            },
        }
    },
)
async def get_velocity_class(
    velocity_class_id: int,
    service: ProductDataService = Depends(get_product_data_service),
) -> VelocityClassResponse:
    """Return a single velocity class by its unique identifier.

    Args:
        velocity_class_id: The numeric velocity class ID to look up.
        service: Injected :class:`ProductDataService` singleton.

    Returns:
        A :class:`VelocityClassResponse` for the matching class.

    Raises:
        HTTPException: 404 if no class with ``velocity_class_id`` exists.
    """
    for vc in service.get_velocity_classes():
        if vc["velocity_class_id"] == velocity_class_id:
            return VelocityClassResponse(**vc)

    raise HTTPException(
        status_code=404,
        detail=f"Velocity class with id {velocity_class_id} not found.",
    )


# ============================================================================
# Products — Get by ID  (dynamic path — MUST be AFTER all static paths)
# ============================================================================


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get a product by ID",
    description=(
        "Returns a single product record identified by its unique "
        "``product_id``.  Returns HTTP 404 if no product with the given ID "
        "exists in the catalogue."
    ),
    responses={
        404: {
            "description": "Product not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Product with id 99999 not found."}
                }
            },
        }
    },
)
async def get_product(
    product_id: int,
    service: ProductDataService = Depends(get_product_data_service),
) -> ProductResponse:
    """Return a single product by its unique identifier.

    Args:
        product_id: The numeric product ID to look up.
        service: Injected :class:`ProductDataService` singleton.

    Returns:
        A :class:`ProductResponse` for the matching product.

    Raises:
        HTTPException: 404 if no product with ``product_id`` exists.
    """
    for product in service.get_products():
        if product["product_id"] == product_id:
            return ProductResponse(**product)

    raise HTTPException(
        status_code=404,
        detail=f"Product with id {product_id} not found.",
    )