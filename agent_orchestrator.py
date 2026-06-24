"""Agent Orchestrator - Coordinates all agents in the Inventory Management System."""

from __future__ import annotations

import logging
from typing import Optional

from agents.inventory_monitoring import InventoryMonitoringAgent
from agents.replenishment_planning import ReplenishmentPlanningAgent
from config import AzureOpenAIClient, AzureOpenAIConfig

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrates the execution of all agents in the IMS workflow.
    
    Workflow:
    - Phase 1-3: InventoryMonitoringAgent (Inventory Event Snapshots → Calculation → Risk Monitoring)
    - Phase 4: ReplenishmentPlanningAgent (Consumes risk assessments → Generates orders)
    
    Future phases (5-6) will be added here as they're developed.
    """

    def __init__(
        self,
        inventory_monitoring_agent: Optional[InventoryMonitoringAgent] = None,
        replenishment_planning_agent: Optional[ReplenishmentPlanningAgent] = None,
        openai_client: Optional[AzureOpenAIClient] = None,
    ) -> None:
        self.inventory_agent = inventory_monitoring_agent or InventoryMonitoringAgent(
            openai_client=openai_client
        )
        self.replenishment_agent = replenishment_planning_agent or ReplenishmentPlanningAgent(
            openai_client=openai_client
        )
        logger.info("AgentOrchestrator initialized")

    def execute(self) -> dict[str, object]:
        """
        Execute the complete workflow: Phases 1-4.
        
        Returns:
            Dictionary with results from all phases
        """
        try:
            logger.info("="*100)
            logger.info("AGENT ORCHESTRATOR - STARTING COMPLETE IMS WORKFLOW (PHASES 1-4)")
            logger.info("="*100)
            
            # Phase 1-3: Inventory Monitoring
            logger.info("\n[PHASES 1-3] Executing Inventory Monitoring Agent...")
            inventory_results = self.inventory_agent.execute()
            
            risk_assessments = inventory_results.get("assessments", [])
            logger.info(f"  Completed: Generated {len(risk_assessments)} risk assessments")
            
            # Phase 4: Replenishment Planning
            logger.info("\n[PHASE 4] Executing Replenishment Planning Agent...")
            replenishment_results = self.replenishment_agent.execute(risk_assessments)
            
            orders = replenishment_results.get("orders", [])
            logger.info(f"  Completed: Generated {len(orders)} replenishment orders")
            
            logger.info("\n" + "="*100)
            logger.info("AGENT ORCHESTRATOR - COMPLETE IMS WORKFLOW FINISHED")
            logger.info("="*100)
            
            return {
                "workflow_status": "COMPLETE",
                "phases_executed": [1, 2, 3, 4],
                "phase_1_3_results": inventory_results,
                "phase_4_results": replenishment_results,
                "summary": self._build_workflow_summary(
                    inventory_results,
                    replenishment_results,
                ),
            }
        except Exception as e:
            logger.error(f"Error in orchestrator workflow: {e}", exc_info=True)
            raise

    def _build_workflow_summary(
        self,
        inventory_results: dict,
        replenishment_results: dict,
    ) -> str:
        """Build summary of entire workflow."""
        lines = [
            "INVENTORY MANAGEMENT SYSTEM - COMPLETE WORKFLOW SUMMARY",
            "="*80,
            "",
            "PHASE 1-3: INVENTORY MONITORING AGENT",
            f"  - Risk Assessments: {len(inventory_results.get('assessments', []))}",
            f"  - Inventory Positions: {len(inventory_results.get('calculations', []))}",
            "",
            "PHASE 4: REPLENISHMENT PLANNING AGENT",
            f"  - Replenishment Orders: {len(replenishment_results.get('orders', []))}",
            f"  - Risky Items Processed: {replenishment_results.get('risky_items_processed', 0)}",
        ]
        
        if replenishment_results.get("summary"):
            summary = replenishment_results["summary"]
            lines.extend([
                f"  - Total Order Cost: ${summary.total_order_cost:.2f}",
                f"  - Urgent Orders: {summary.orders_by_priority.get('URGENT', 0)}",
                f"  - High Priority: {summary.orders_by_priority.get('HIGH', 0)}",
                f"  - Avg Lead Time: {summary.average_lead_time:.1f} days",
            ])
        
        lines.append("="*80)
        return "\n".join(lines)
