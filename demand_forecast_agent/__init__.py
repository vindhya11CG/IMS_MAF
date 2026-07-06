"""Demand Forecast Agent services.

Consolidated from 14 files down to 6:
  - feature_engineering_service.py  (FeatureEngineeringService)   [shared with training]
  - core_forecasting_service.py     (ModelLoaderService, ForecastService,
                                      BatchForecastService, ConfidenceService,
                                      LoggingService)
  - decision_services.py            (InputValidatorService,
                                      InventoryDecisionService, ReorderService,
                                      OutputFormatterService)
  - azure_services.py               (AzureConfigService, ExplanationService)
  - demand_forecast_workflow_service.py (DemandForecastWorkflow orchestrator)
  - base_service.py                 (AgentService ABC)
"""
from demand_forecast_agent.services.base_service import AgentService
from demand_forecast_agent.services.feature_engineering_service import FeatureEngineeringService
from demand_forecast_agent.services.core_forecasting_service import (
    ModelLoaderService,
    ForecastService,
    BatchForecastService,
    ConfidenceService,
    LoggingService,
)
from demand_forecast_agent.services.decision_services import (
    InputValidatorService,
    InventoryDecisionService,
    ReorderService,
    OutputFormatterService,
)
from demand_forecast_agent.services.azure_services import AzureConfigService, ExplanationService
from demand_forecast_agent.services.demand_forecast_workflow_service import DemandForecastWorkflow
from demand_forecast_agent.agent import DemandForecastAgent
__all__ = [
    "AgentService",
    "FeatureEngineeringService",
    "ModelLoaderService",
    "ForecastService",
    "BatchForecastService",
    "ConfidenceService",
    "LoggingService",
    "InputValidatorService",
    "InventoryDecisionService",
    "ReorderService",
    "OutputFormatterService",
    "AzureConfigService",
    "ExplanationService",
    "DemandForecastWorkflow",
    "DemandForecastAgent",
]