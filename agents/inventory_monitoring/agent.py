from __future__ import annotations

import logging
from typing import List, Optional

from utils.csv_loader import CsvInventoryDataLoader
from config import AzureOpenAIClient, AzureOpenAIConfig
from .models import InventoryCalculationResult, InventoryPosition, RiskAssessment, WeatherFestivalContext
from .services import (
    AgentService,
    EventSnapshotService,
    InventoryCalculationService,
    InventoryRiskMonitoringService,
)

logger = logging.getLogger(__name__)


class InventoryMonitoringAgent(AgentService):
    """Agent core for inventory monitoring and risk analysis.

    Phase 6 extension: loads weather/festival context from the db6 tables
    (or the LFS dataset when available) and feeds it into the risk
    monitoring service so weather/festival signals influence demand
    estimates and risk assessments.
    """

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
            
            # Load weather/festival context (Phase 6)
            logger.info("\n[PHASE 1b] Loading weather/festival context...")
            weather_context_map = self.loader.build_weather_context_map()
            weather_context_loaded = len(weather_context_map)
            logger.info(f"  Weather context entries loaded: {weather_context_loaded}")

            logger.info(f"\nData Summary:")
            logger.info(f"  Positions: {len(positions)}")
            logger.info(f"  Valid Snapshots: {len(valid_snapshots)}")
            logger.info(f"  In-Transit Items: {len(in_transit)}")
            logger.info(f"  Weather Context Entries: {weather_context_loaded}")

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
                weather_context_map=weather_context_map if weather_context_loaded > 0 else None,
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
                "weather_context_loaded": weather_context_loaded,
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
            "Weather and festival context is included where available — factor these into your analysis.",
            "",
            "Top risk records:",
        ]

        for assessment in top_risks:
            line = (
                f"SKU {assessment.sku_id} @ Location {assessment.location_id}: "
                f"current_stock={assessment.current_stock}, "
                f"safety_stock={assessment.safety_stock}, "
                f"reorder_point={assessment.reorder_point}, "
                f"in_transit={assessment.in_transit_qty}, "
                f"forecasted_demand={assessment.forecasted_demand}, "
                f"projected_stock={assessment.projected_stock}, "
                f"risk_reasons={assessment.risk_reasons}"
            )
            # Append weather context summary if available
            wx = assessment.weather_context
            if wx is not None:
                line += (
                    f", weather_multiplier={wx.effective_demand_multiplier():.2f}"
                    f", severity={wx.weather_severity_index:.2f}"
                    f", festival={wx.is_festival_day}"
                    f", season={wx.season or 'N/A'}"
                )
            prompt_lines.append(line)

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
        
        wx_risks = [a for a in detected if a.weather_context is not None and a.weather_context.is_high_risk()]
        actions = {a.recommended_action for a in detected}
        summary_lines = [
            f"Inventory Risk Summary: {len(detected)} positions at risk out of {len(assessments)} monitored",
        ]
        if wx_risks:
            summary_lines.append(
                f"  Weather/Festival-triggered risks: {len(wx_risks)} positions"
            )
        summary_lines.append("")
        summary_lines.append("Recommended Actions:")
        for action in sorted(actions):
            summary_lines.append(f"- {action}")
        
        return "\n".join(summary_lines)
