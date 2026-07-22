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


def parse_float(value: Optional[str | int | float], default: float = 0.0) -> float:
    """Parse a string or numeric value to float with fallback to default."""
    if value is None:
        return default
    if isinstance(value, Number):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    if not isinstance(value, str):
        return default
    value = value.strip().replace("\ufeff", "")
    if value == "" or value.upper() in {"NULL", "NONE"}:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def parse_bool(value: Optional[str | int | float | bool], default: bool = False) -> bool:
    """Parse common boolean representations from CSV values."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, Number):
        return bool(int(value))
    if isinstance(value, str):
        normalized = value.strip().replace("\ufeff", "").lower()
        if normalized in {"true", "1", "yes", "y", "t"}:
            return True
        if normalized in {"false", "0", "no", "n", "f"}:
            return False
    return default
