"""Utility functions for parsing CSV data."""

from typing import Optional


from numbers import Number

def parse_int(value: Optional[str | int | float], default: int = 0) -> int:
    """Parse a string or numeric value to integer with fallback to default."""
    if value is None:
        return default
    if isinstance(value, Number):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    if not isinstance(value, str):
        return default
    value = value.strip().replace("\ufeff", "")
    if value == "" or value.upper() in {"NULL", "NONE"}:
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def parse_optional_int(value: Optional[str | int | float]) -> Optional[int]:
    """Parse a string or numeric value to optional integer."""
    if value is None:
        return None
    if isinstance(value, Number):
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, str):
        return None
    value = value.strip().replace("\ufeff", "")
    if value == "" or value.upper() in {"NULL", "NONE"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None
