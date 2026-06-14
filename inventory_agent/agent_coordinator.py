from __future__ import annotations

from typing import List, Optional, Tuple

from .azure_openai_client import AzureOpenAIClient, AzureOpenAIConfig
from .data_loader import CsvInventoryDataLoader
from .inventory_calculation_service import InventoryCalculationService
from .inventory_risk_monitoring_service import InventoryRiskMonitoringService
from .models import InventoryCalculationResult, InventoryPosition, RiskAssessment
from .service_base import AgentService


class InventoryMonitoringAgent(AgentService):
    """Agent core for inventory monitoring and risk analysis."""

    def __init__(
        self,
        loader: Optional[CsvInventoryDataLoader] = None,
        calculation_service: Optional[InventoryCalculationService] = None,
        risk_service: Optional[InventoryRiskMonitoringService] = None,
        openai_client: Optional[AzureOpenAIClient] = None,
    ) -> None:
        super().__init__(name="InventoryMonitoringAgent")
        self.loader = loader or CsvInventoryDataLoader()
        self.calculation_service = calculation_service or InventoryCalculationService()
        self.risk_service = risk_service or InventoryRiskMonitoringService()
        self.openai_client = openai_client

    def execute(self) -> dict[str, object]:
        positions = self.loader.load_inventory_positions()
        snapshots = self.loader.load_inventory_daily_snapshots()
        in_transit = self.loader.load_in_transit_inventory()

        calculation_results = self.calculation_service.execute(positions, snapshots)
        forecasted_demand = self.risk_service.estimate_forecasted_demand(calculation_results)
        assessments = self.risk_service.execute(
            positions,
            calculation_results,
            in_transit,
            forecasted_demand,
        )

        summary = self._generate_local_summary(assessments)
        azure_analysis = None
        if self.openai_client is not None:
            messages = [
                self.openai_client.build_system_message(),
                {
                    "role": "user",
                    "content": self._build_openai_prompt(assessments),
                },
            ]
            azure_analysis = self.openai_client.create_chat_completion(messages)

        return {
            "calculations": calculation_results,
            "assessments": assessments,
            "summary": summary,
            "azure_analysis": azure_analysis,
        }

    def _build_openai_prompt(self, assessments: List[RiskAssessment]) -> str:
        top_risks = self._get_top_risk_assessments(assessments)
        prompt_lines = [
            "Evaluate the following inventory risk conditions and provide a concise recommendation.",
            "Include the likely cause of risk and the next action for the replenishment planning agent.",
            "",
            "Top risk records:",
        ]

        for assessment in top_risks:
            prompt_lines.append(
                f"SKU {assessment.sku_id} @ Location {assessment.location_id}: "
                f"current_stock={assessment.current_stock}, "
                f"safety_stock={assessment.safety_stock}, "
                f"reorder_point={assessment.reorder_point}, "
                f"in_transit={assessment.in_transit_qty}, "
                f"forecasted_demand={assessment.forecasted_demand}, "
                f"projected_stock={assessment.projected_stock}, "
                f"risk_reasons={assessment.risk_reasons}"
            )

        return "\n".join(prompt_lines)

    def _get_top_risk_assessments(self, assessments: List[RiskAssessment]) -> List[RiskAssessment]:
        return sorted(
            assessments,
            key=lambda a: (
                a.risk_detected,
                -a.current_stock,
                -a.projected_stock,
            ),
            reverse=True,
        )[:10]

    def _generate_local_summary(self, assessments: List[RiskAssessment]) -> str:
        detected = [a for a in assessments if a.risk_detected]
        if not detected:
            return "No inventory risk detected across monitored positions."
        actions = {a.recommended_action for a in detected}
        return (
            f"{len(detected)} risk conditions detected. "
            f"Primary actions: {', '.join(actions)}."
        )
