"""Utility functions for parsing CSV data."""

from typing import Optional


def parse_int(value: Optional[str], default: int = 0) -> int:
    """Parse a string value to integer with fallback to default."""
    if value is None:
        return default
    value = value.strip().replace("\ufeff", "")
    if value == "" or value.upper() in {"NULL", "NONE"}:
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def parse_optional_int(value: Optional[str]) -> Optional[int]:
    """Parse a string value to optional integer."""
    if value is None:
        return None
    value = value.strip().replace("\ufeff", "")
    if value == "" or value.upper() in {"NULL", "NONE"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None
