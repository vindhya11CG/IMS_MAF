from __future__ import annotations

from typing import TYPE_CHECKING

from .state import state, AppState

if TYPE_CHECKING:
    from api.v1.services.forecasting_service import ForecastingService


def get_app_state() -> AppState:
    """FastAPI dependency to inject the global application state."""
    return state


def get_forecast_service() -> "ForecastingService":
    """FastAPI dependency that returns the global ForecastingService singleton.

    Import is deferred to avoid circular imports at module load time.
    The singleton is initialised lazily on first request.
    """
    from api.v1.services.forecasting_service import get_forecasting_service

    return get_forecasting_service()
