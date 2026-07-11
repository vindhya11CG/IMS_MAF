"""Pydantic response schemas for product-domain API endpoints.

This module defines the data contracts for all resources served by the
products router:

* :class:`ProductResponse` — individual product (SKU) record.
* :class:`ProductCategoryResponse` — product category reference data.
* :class:`SeasonalPatternResponse` — seasonal demand multiplier record.
* :class:`VelocityClassResponse` — velocity classification tier.
* :class:`PaginatedProductResponse` — paginated wrapper for product lists.

All schemas derive from :class:`pydantic.BaseModel` with ``from_attributes``
enabled so they can be constructed from ORM-style objects *or* plain dicts.
"""

from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class ProductResponse(BaseModel):
    """Schema representing a single product (SKU) from the product master.

    Maps 1-to-1 with every column in ``products.csv``.

    Attributes:
        product_id: Unique numeric identifier for the product.
        product_code: Human-readable SKU code (e.g. ``"ELEC-1001"``).
        product_name: Descriptive product name.
        category_id: Foreign key to the product category.
        velocity_class_id: Foreign key to the velocity classification tier.
        avg_retail_price: Average retail selling price in USD.
        weight_lbs: Product weight in pounds.
        shelf_life_days: Shelf life in days; ``None`` for non-perishable items.
        supplier_id: Foreign key to the primary supplier.
    """

    model_config = ConfigDict(from_attributes=True)

    product_id: int = Field(
        ..., description="Unique numeric identifier for the product.", examples=[1]
    )
    product_code: str = Field(
        ..., description="Human-readable SKU code.", examples=["ELEC-1001"]
    )
    product_name: str = Field(
        ..., description="Descriptive product name.", examples=["Toaster 4-Slice v1"]
    )
    category_id: int = Field(
        ..., description="Foreign key to the product category.", examples=[1]
    )
    velocity_class_id: int = Field(
        ...,
        description="Foreign key to the velocity classification tier.",
        examples=[1],
    )
    avg_retail_price: float = Field(
        ..., description="Average retail selling price in USD.", examples=[199.0]
    )
    weight_lbs: float = Field(
        ..., description="Product weight in pounds.", examples=[39.38]
    )
    shelf_life_days: Optional[int] = Field(
        None,
        description="Shelf life in days. Null for non-perishable items.",
        examples=[14],
    )
    supplier_id: int = Field(
        ..., description="Foreign key to the primary supplier.", examples=[14]
    )


# ---------------------------------------------------------------------------
# Product Category
# ---------------------------------------------------------------------------


class ProductCategoryResponse(BaseModel):
    """Schema representing a product category reference record.

    Maps 1-to-1 with every column in ``product_categories.csv``.

    Attributes:
        category_id: Unique numeric identifier for the category.
        category_code: Short code (e.g. ``"ELEC"``, ``"GROC"``).
        category_name: Full category name.
        avg_retail_price: Average retail price across the category in USD.
        shelf_life_days: Typical shelf life; ``None`` for non-perishable categories.
        temperature_controlled: Whether the category requires temperature control.
        hazmat_flag: Whether the category contains hazardous materials.
        typical_velocity: Typical velocity class letter (``"A"``, ``"B"``, etc.).
    """

    model_config = ConfigDict(from_attributes=True)

    category_id: int = Field(
        ..., description="Unique numeric identifier for the category.", examples=[1]
    )
    category_code: str = Field(
        ..., description="Short alphanumeric category code.", examples=["ELEC"]
    )
    category_name: str = Field(
        ..., description="Full category name.", examples=["Electronics"]
    )
    avg_retail_price: float = Field(
        ...,
        description="Average retail price across the category in USD.",
        examples=[549.99],
    )
    shelf_life_days: Optional[int] = Field(
        None,
        description="Typical shelf life in days. Null for non-perishable categories.",
        examples=[14],
    )
    temperature_controlled: bool = Field(
        ...,
        description="Whether the category requires temperature control.",
        examples=[False],
    )
    hazmat_flag: bool = Field(
        ...,
        description="Whether the category contains hazardous materials.",
        examples=[True],
    )
    typical_velocity: str = Field(
        ...,
        description="Typical velocity class letter (A = high, B = medium, C = low).",
        examples=["A"],
    )


# ---------------------------------------------------------------------------
# Seasonal Pattern
# ---------------------------------------------------------------------------


class SeasonalPatternResponse(BaseModel):
    """Schema representing a seasonal demand pattern.

    Maps 1-to-1 with every column in ``seasonal_patterns.csv``.

    Attributes:
        season_id: Unique numeric identifier for the season.
        season_name: Human-readable season name.
        start_month: Starting calendar month (1–12).
        end_month: Ending calendar month (1–12).
        demand_multiplier: Multiplicative factor applied to baseline demand.
        description: Free-text description of the seasonal effect.
    """

    model_config = ConfigDict(from_attributes=True)

    season_id: int = Field(
        ..., description="Unique numeric identifier for the season.", examples=[1]
    )
    season_name: str = Field(
        ..., description="Human-readable season name.", examples=["Regular"]
    )
    start_month: int = Field(
        ..., ge=1, le=12, description="Starting calendar month (1–12).", examples=[1]
    )
    end_month: int = Field(
        ..., ge=1, le=12, description="Ending calendar month (1–12).", examples=[8]
    )
    demand_multiplier: float = Field(
        ...,
        description="Multiplicative factor applied to baseline demand.",
        examples=[1.0],
    )
    description: str = Field(
        ...,
        description="Free-text description of the seasonal effect.",
        examples=["Standard baseline demand period"],
    )


# ---------------------------------------------------------------------------
# Velocity Class
# ---------------------------------------------------------------------------


class VelocityClassResponse(BaseModel):
    """Schema representing a product velocity classification tier.

    Maps 1-to-1 with every column in ``velocity_classes.csv``.

    Attributes:
        velocity_class_id: Unique numeric identifier for the velocity tier.
        velocity_code: Single-letter code (``"A"``, ``"B"``, ``"C"``).
        velocity_name: Descriptive tier name.
        annual_units_min: Minimum annual unit sales for this tier.
        annual_units_max: Maximum annual unit sales for this tier.
        description: Free-text description of the tier's characteristics.
    """

    model_config = ConfigDict(from_attributes=True)

    velocity_class_id: int = Field(
        ...,
        description="Unique numeric identifier for the velocity tier.",
        examples=[1],
    )
    velocity_code: str = Field(
        ..., description="Single-letter velocity code.", examples=["A"]
    )
    velocity_name: str = Field(
        ..., description="Descriptive tier name.", examples=["High Velocity"]
    )
    annual_units_min: int = Field(
        ...,
        description="Minimum annual unit sales for this tier.",
        examples=[50000],
    )
    annual_units_max: int = Field(
        ...,
        description="Maximum annual unit sales for this tier.",
        examples=[999999],
    )
    description: str = Field(
        ...,
        description="Free-text description of the tier's characteristics.",
        examples=["Fast-moving items with high annual turnover"],
    )


# ---------------------------------------------------------------------------
# Pagination Wrapper
# ---------------------------------------------------------------------------


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response envelope.

    Wraps a list of items with pagination metadata so clients can
    iterate through large result sets efficiently.

    Attributes:
        items: The page of results.
        total: Total number of matching records across all pages.
        page: Current 1-indexed page number.
        page_size: Maximum number of items per page.
        total_pages: Total number of pages available.
    """

    items: List[T] = Field(..., description="The page of results.")
    total: int = Field(
        ..., description="Total number of matching records across all pages."
    )
    page: int = Field(..., description="Current 1-indexed page number.")
    page_size: int = Field(
        ..., description="Maximum number of items per page."
    )
    total_pages: int = Field(
        ..., description="Total number of pages available."
    )


# Concrete pagination type for Swagger/OpenAPI schema generation.
PaginatedProductResponse = PaginatedResponse[ProductResponse]


# ---------------------------------------------------------------------------
# Forecast Flagged Product
# ---------------------------------------------------------------------------


class ForecastFlaggedProductResponse(ProductResponse):
    """Schema representing a product flagged by the demand forecast service,
    including the forecast/risk details that triggered the flag.
    """

    location_id: int = Field(
        ..., description="Unique numeric identifier for the location.", examples=[1]
    )
    location_name: str = Field(
        ..., description="Descriptive name of the location.", examples=["DC Chicago"]
    )
    current_stock: int = Field(
        ..., description="The current computed stock level at the location.", examples=[45]
    )
    safety_stock: int = Field(
        ..., description="The safety stock threshold for this product.", examples=[50]
    )
    reorder_point: int = Field(
        ..., description="The reorder point threshold for this product.", examples=[100]
    )
    forecasted_demand: int = Field(
        ..., description="The estimated forecasted demand for this product.", examples=[15]
    )
    projected_stock: int = Field(
        ..., description="The projected stock level after accounting for forecasted demand.", examples=[-5]
    )
    risk_reasons: List[str] = Field(
        ...,
        description="List of reasons why this product is flagged.",
        examples=[["Projected stock falls below safety stock after forecasted demand."]],
    )


# Concrete pagination type for Swagger/OpenAPI schema generation.
PaginatedForecastFlaggedProductResponse = PaginatedResponse[ForecastFlaggedProductResponse]

