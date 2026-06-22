from __future__ import annotations

import logging
from typing import List, Optional

from utils.csv_loader import CsvInventoryDataLoader
from config import AzureOpenAIClient, AzureOpenAIConfig
from .models import InventoryCalculationResult, InventoryPosition, RiskAssessment
from .services import (
    AgentService,
    EventSnapshotService,
    InventoryCalculationService,
    InventoryRiskMonitoringService,
)

logger = logging.getLogger(__name__)


class InventoryMonitoringAgent(AgentService):
    """Agent core for inventory monitoring and risk analysis."""

    def __init__(
        self,
        loader: Optional[CsvInventoryDataLoader] = None,
        event_snapshot_service: Optional[EventSnapshotService] = None,
        calculation_service: Optional[InventoryCalculationService] = None,
        risk_service: Optional[InventoryRiskMonitoringService] = None,
        openai_client: Optional[AzureOpenAIClient] = None,
    ) -> None:
        super().__init__(name="InventoryMonitoringAgent")
        self.loader = loader or CsvInventoryDataLoader()
        self.event_snapshot_service = event_snapshot_service or EventSnapshotService(self.loader)
        self.calculation_service = calculation_service or InventoryCalculationService()
        self.risk_service = risk_service or InventoryRiskMonitoringService()
        self.openai_client = openai_client
        logger.info("InventoryMonitoringAgent initialized")

    def execute(self) -> dict[str, object]:
        """Execute the inventory monitoring workflow: Phase 1 → Phase 2 → Phase 3."""
        try:
            logger.info("="*80)
            logger.info("INVENTORY MONITORING AGENT - STARTING WORKFLOW")
            logger.info("="*80)
            
            # Phase 1: Load and validate inventory event snapshots
            logger.info("\n[PHASE 1] Loading inventory event snapshots...")
            snapshot_result = self.event_snapshot_service.execute()
            valid_snapshots = snapshot_result.valid_snapshots
            
            # Load other required data
            positions = [
                position if isinstance(position, InventoryPosition) else InventoryPosition(**position)
                for position in self.loader.load_inventory_positions()
            ]
            in_transit = self.loader.load_in_transit_inventory()
            
            logger.info(f"\nData Summary:")
            logger.info(f"  Positions: {len(positions)}")
            logger.info(f"  Valid Snapshots: {len(valid_snapshots)}")
            logger.info(f"  In-Transit Items: {len(in_transit)}")

            # Phase 2: Calculate inventory
            logger.info("\n[PHASE 2] Calculating current inventory...")
            calculation_results = self.calculation_service.execute(positions, valid_snapshots)
            logger.info(f"  Calculated: {len(calculation_results)} position calculations")

            # Phase 3: Estimate demand and assess risk
            logger.info("\n[PHASE 3] Assessing inventory risk...")
            forecasted_demand = self.risk_service.estimate_forecasted_demand(calculation_results)
            assessments = self.risk_service.execute(
                positions,
                calculation_results,
                in_transit,
                forecasted_demand,
            )
            logger.info(f"  Risk Assessments: {len(assessments)}")

            # Generate summary
            summary = self._generate_local_summary(assessments)
            azure_analysis = None
            
            if self.openai_client is not None:
                logger.info("\n[AZURE ANALYSIS] Sending risk data to Azure OpenAI...")
                messages = [
                    self.openai_client.build_system_message(),
                    {
                        "role": "user",
                        "content": self._build_openai_prompt(assessments),
                    },
                ]
                azure_analysis = self.openai_client.create_chat_completion(messages)
                logger.info("  Analysis complete")
            
            logger.info("\n" + "="*80)
            logger.info("INVENTORY MONITORING AGENT - WORKFLOW COMPLETE")
            logger.info("="*80)

            return {
                "phase1_snapshots": valid_snapshots,
                "calculations": calculation_results,
                "assessments": assessments,
                "summary": summary,
                "azure_analysis": azure_analysis,
            }
        except Exception as e:
            logger.error(f"Error in inventory monitoring workflow: {e}", exc_info=True)
            raise

    def _build_openai_prompt(self, assessments: List[RiskAssessment]) -> str:
        """Build prompt for Azure OpenAI analysis."""
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
        """Get top 10 risk assessments for reporting."""
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
        """Generate a summary of risk assessment results."""
        detected = [a for a in assessments if a.risk_detected]
        if not detected:
            return "No inventory risk detected across monitored positions."
        
        actions = {a.recommended_action for a in detected}
        summary_lines = [
            f"Inventory Risk Summary: {len(detected)} positions at risk out of {len(assessments)} monitored",
            "",
            "Recommended Actions:",
        ]
        for action in sorted(actions):
            summary_lines.append(f"- {action}")
        
        return "\n".join(summary_lines)
