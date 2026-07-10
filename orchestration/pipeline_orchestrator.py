from __future__ import annotations
 
import dataclasses
import logging
import os
from typing import Dict, List, Optional, Tuple
 
from agents import (
    InventoryMonitoringAgent,
    ReplenishmentPlanningAgent,
    SupplierSelectionAgent,
)
from agents.inventory_monitoring.models import RiskAssessment
from demand_forecast_agent import DemandForecastAgent
from utils.csv_loader import CsvInventoryDataLoader
from config import AzureOpenAIClient, AzureOpenAIConfig
 
logger = logging.getLogger(__name__)
 
# Caps how many risky rows get an ML forecast call per run. Keeps dev/demo
# runs fast and bounded; raise (or remove the cap) for a full overnight
# batch run. Override with the MAX_ML_FORECAST_CALLS env var.
DEFAULT_MAX_ML_FORECAST_CALLS = int(os.getenv("MAX_ML_FORECAST_CALLS", "200"))
 
 
class PipelineOrchestrator:
 
    def __init__(
        self,
        loader: Optional[CsvInventoryDataLoader] = None,
        use_azure: bool = False,
        max_ml_forecast_calls: int = DEFAULT_MAX_ML_FORECAST_CALLS,
    ) -> None:
        self.loader = loader or CsvInventoryDataLoader()
        self.max_ml_forecast_calls = max_ml_forecast_calls
 
        # Single toggle for Azure testing: use_azure=True wires the same
        # AzureOpenAIClient into all three unmodified agents (each already
        # accepts an optional openai_client=... constructor arg) - no code
        # changes needed in those agents to test Azure on/off.
        openai_client = self._build_azure_client() if use_azure else None
 
        self.inventory_agent = InventoryMonitoringAgent(
            loader=self.loader, openai_client=openai_client
        )
        self.replenishment_agent = ReplenishmentPlanningAgent(
            loader=self.loader, openai_client=openai_client
        )
        self.supplier_agent = SupplierSelectionAgent(
            loader=self.loader, openai_client=openai_client
        )
        self.demand_forecast_agent = DemandForecastAgent()
 
        # Lookup tables used to build DemandForecastAgent payloads from a
        # RiskAssessment, which doesn't itself carry allocated_qty or
        # product attributes (price/category/velocity).
        self._allocated_qty_by_key = self._load_allocated_qty_lookup()
        self._product_attrs_by_sku = self._load_product_attrs_lookup()
 
    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_azure_client() -> Optional["AzureOpenAIClient"]:
        try:
            config = AzureOpenAIConfig.from_env()
            return AzureOpenAIClient(config)
        except Exception as e:
            logger.warning(f"Azure OpenAI not configured, continuing without it: {e}")
            return None
 
    def _load_allocated_qty_lookup(self) -> Dict[Tuple[int, int], int]:
        """NOTE: adjust this if CsvInventoryDataLoader's method/field names
        differ from what's used elsewhere in your codebase - this and
        _load_product_attrs_lookup below are the only two loader-specific
        touchpoints in this file."""
        lookup: Dict[Tuple[int, int], int] = {}
        try:
            for position in self.loader.load_inventory_positions():
                if isinstance(position, dict):
                    sku_id = position.get("sku_id") or position.get("product_id")
                    location_id = position.get("location_id")
                    allocated = position.get("allocated_qty", 0)
                else:
                    sku_id = getattr(position, "sku_id", None)
                    location_id = getattr(position, "location_id", None)
                    allocated = getattr(position, "allocated_qty", 0)
                if sku_id is not None and location_id is not None:
                    lookup[(sku_id, location_id)] = allocated or 0
        except Exception as e:
            logger.warning(f"Could not build allocated_qty lookup: {e}")
        return lookup
 
    def _load_product_attrs_lookup(self) -> Dict[int, dict]:
        lookup: Dict[int, dict] = {}
        try:
            for product in self.loader.load_products():
                sku_id = product.get("sku_id") or product.get("product_id")
                if sku_id is not None:
                    lookup[sku_id] = product
        except Exception as e:
            logger.warning(f"Could not build product attribute lookup: {e}")
        return lookup
 
    # ------------------------------------------------------------------
    # RiskAssessment -> DemandForecastAgent payload
    # ------------------------------------------------------------------
    def _build_forecast_payload(self, assessment: RiskAssessment) -> dict:
        product = self._product_attrs_by_sku.get(assessment.sku_id, {})
        allocated_qty = self._allocated_qty_by_key.get(
            (assessment.sku_id, assessment.location_id), 0
        )
        payload = {
            "product_id": assessment.sku_id,
            "location_id": assessment.location_id,
            "on_hand_qty": assessment.current_stock,
            "allocated_qty": allocated_qty,
            "safety_stock_qty": assessment.safety_stock,
            "reorder_point_qty": assessment.reorder_point,
        }
        # Best-effort enrichment - FeatureEngineeringService.to_model_matrix
        # fills anything absent with 0 at reindex time, so these are
        # optional, not required.
        for key in ("avg_retail_price", "category_id", "velocity_class_id"):
            if key in product:
                payload[key] = product[key]
        return payload
 
    def _enhance_assessment_with_ml_forecast(
        self, assessment: RiskAssessment
    ) -> Tuple[RiskAssessment, bool, dict]:
        """Returns (possibly-updated assessment, was_enhanced, detail).
 
        `detail` is a small, JSON-safe summary of what the Demand Forecast
        Agent did for this one sku/location. It exists purely so callers
        (e.g. a demo/smoke-test script) can show a concise Demand Forecast
        Agent section - sku, location, heuristic vs. ML forecast,
        confidence, and pass/fail status - without reaching into internal
        DemandForecastAgent objects or re-running anything.
        """
        payload = self._build_forecast_payload(assessment)
        heuristic_forecast = assessment.forecasted_demand
        result = self.demand_forecast_agent.execute(payload, horizon=14)
 
        if "forecast" not in result or not hasattr(result["forecast"], "forecasted_demand"):
            # Inference failed validation or the model itself - keep the
            # heuristic assessment rather than silently dropping the row.
            reason = result.get("message", str(result)) if isinstance(result, dict) else str(result)
            logger.warning(
                f"ML forecast unavailable for sku={assessment.sku_id} "
                f"loc={assessment.location_id}: {result}. Keeping heuristic forecast."
            )
            detail = {
                "sku_id": assessment.sku_id,
                "location_id": assessment.location_id,
                "status": "FALLBACK_TO_HEURISTIC",
                "reason": reason,
                "heuristic_forecasted_demand": heuristic_forecast,
                "ml_forecasted_demand": None,
                "confidence": None,
                "model_used": None,
                "risk_status_before": assessment.risk_detected,
                "risk_status_after": assessment.risk_detected,
            }
            return assessment, False, detail
 
        forecast_result = result["forecast"]
        ml_forecast = forecast_result.forecasted_demand
 
        projected_stock = int(
            round(assessment.current_stock + assessment.in_transit_qty - ml_forecast)
        )
        risk_detected = (
            assessment.current_stock <= assessment.reorder_point
            or assessment.current_stock <= assessment.safety_stock
            or projected_stock < assessment.safety_stock
        )
 
        risk_reasons = list(assessment.risk_reasons)
        if risk_detected != assessment.risk_detected:
            risk_reasons.append(
                "ML forecast reassessment changed risk status "
                f"(heuristic={assessment.risk_detected} -> ml={risk_detected})"
            )
 
        enhanced = dataclasses.replace(
            assessment,
            forecasted_demand=int(round(ml_forecast)),
            projected_stock=projected_stock,
            risk_detected=risk_detected,
            risk_reasons=risk_reasons,
        )
 
        detail = {
            "sku_id": assessment.sku_id,
            "location_id": assessment.location_id,
            "status": "SUCCESS",
            "reason": None,
            "heuristic_forecasted_demand": heuristic_forecast,
            "ml_forecasted_demand": round(float(ml_forecast), 2),
            "confidence": getattr(forecast_result, "confidence", None),
            "model_used": getattr(forecast_result, "model_used", None),
            "risk_status_before": assessment.risk_detected,
            "risk_status_after": risk_detected,
        }
        return enhanced, True, detail
 
    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def run(self) -> dict:
        logger.info("=" * 80)
        logger.info("PIPELINE ORCHESTRATOR - START")
        logger.info("=" * 80)
 
        # Step 1: Inventory Monitoring (unmodified agent)
        monitoring_result = self.inventory_agent.execute()
        assessments: List[RiskAssessment] = monitoring_result["assessments"]
 
        risky = [a for a in assessments if a.risk_detected]
        capped = risky[: self.max_ml_forecast_calls]
        skipped_due_to_cap = len(risky) - len(capped)
        if skipped_due_to_cap > 0:
            logger.warning(
                f"{len(risky)} risky rows found; scoring the ML model on the "
                f"first {len(capped)} (MAX_ML_FORECAST_CALLS={self.max_ml_forecast_calls}). "
                "Raise the cap for a full batch run."
            )
 
        # Step 2: enhance risky rows with the real ML forecast, and record
        # a per-row detail dict for each one scored this run.
        enhanced_map: Dict[Tuple[int, int], RiskAssessment] = {}
        demand_forecast_details: List[dict] = []
        enhanced_count = 0
        failed_count = 0
        for assessment in capped:
            enhanced, was_enhanced, detail = self._enhance_assessment_with_ml_forecast(assessment)
            enhanced_map[(assessment.sku_id, assessment.location_id)] = enhanced
            demand_forecast_details.append(detail)
            if was_enhanced:
                enhanced_count += 1
            else:
                failed_count += 1
 
        enhanced_assessments = [
            enhanced_map.get((a.sku_id, a.location_id), a) for a in assessments
        ]
 
        # Step 3: Replenishment Planning (unmodified agent, fed enhanced data)
        replenishment_result = self.replenishment_agent.execute(enhanced_assessments)
        orders = replenishment_result["orders"]
 
        # Step 4: Supplier Selection (unmodified agent)
        supplier_result = self.supplier_agent.execute(orders)
 
        logger.info("=" * 80)
        logger.info("PIPELINE ORCHESTRATOR - COMPLETE")
        logger.info("=" * 80)
 
        return {
            "monitoring": monitoring_result,
            "assessments_enhanced_with_ml": enhanced_count,
            "assessments_ml_forecast_failed": failed_count,
            # NEW - see module docstring "CHANGE IN THIS PASS"
            "demand_forecast_details": demand_forecast_details,
            "demand_forecast_skipped_due_to_cap": skipped_due_to_cap,
            "replenishment": replenishment_result,
            "supplier_selection": supplier_result,
        }
 
 
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    orchestrator = PipelineOrchestrator(use_azure=False)
    result = orchestrator.run()
    print("\n=== PIPELINE SUMMARY ===")
    print(f"Assessments enhanced with ML forecast: {result['assessments_enhanced_with_ml']}")
    print(f"ML forecast failures (fell back to heuristic): {result['assessments_ml_forecast_failed']}")
    print(f"Risky rows skipped due to MAX_ML_FORECAST_CALLS cap: {result['demand_forecast_skipped_due_to_cap']}")
    print(f"Replenishment orders generated: {len(result['replenishment']['orders'])}")
    print(f"Supplier selections made: {len(result['supplier_selection']['selections'])}")