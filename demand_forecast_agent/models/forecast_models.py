from dataclasses import dataclass


@dataclass
class ForecastRequest:
    item_id: str
    horizon_days: int


@dataclass
class ForecastResult:
    item_id: str
    forecast_demand: float
    confidence: float
    model_used: str
    horizon_days: int