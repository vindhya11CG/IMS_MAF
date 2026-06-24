"""Main entry point for the Inventory Management System."""

import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent_orchestrator import AgentOrchestrator
from config import AzureOpenAIClient, AzureOpenAIConfig
from utils import setup_logging

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

logger = logging.getLogger(__name__)


def main() -> None:
    """Execute the complete Inventory Management System workflow."""
    # Setup logging
    setup_logging(logging.INFO, log_file="logs/inventory_monitoring.log")
    logger.info("="*80)
    logger.info("Starting Inventory Management System - Complete Workflow (Phases 1-4)")
    logger.info("="*80)
    
    if load_dotenv is not None:
        load_dotenv()

    config = AzureOpenAIConfig.from_env()
    openai_client = None
    
    try:
        openai_client = AzureOpenAIClient(config)
        logger.info("Azure OpenAI client configured successfully")
    except ImportError as e:
        logger.warning(f"Azure OpenAI SDK not available: {e}")
    except ValueError as error:
        logger.warning(f"Azure OpenAI configuration warning: {error}")

    # Execute complete workflow with orchestrator
    orchestrator = AgentOrchestrator(openai_client=openai_client)
    result = orchestrator.execute()

    print("\n" + "="*100)
    print("INVENTORY MANAGEMENT SYSTEM - COMPLETE WORKFLOW RESULTS")
    print("="*100)
    print(result["summary"])
    
    # Phase 1-3 Summary
    inventory_results = result.get("phase_1_3_results", {})
    if inventory_results.get("summary"):
        print("\n" + "="*100)
        print("PHASE 1-3: INVENTORY MONITORING SUMMARY")
        print("="*100)
        print(inventory_results["summary"])
    
    if inventory_results.get("azure_analysis"):
        print("\n" + "="*100)
        print("PHASE 1-3: AZURE OPENAI ANALYSIS")
        print("="*100)
        print(inventory_results["azure_analysis"])
    
    # Phase 4 Summary
    replenishment_results = result.get("phase_4_results", {})
    if replenishment_results.get("summary"):
        summary = replenishment_results["summary"]
        print("\n" + "="*100)
        print("PHASE 4: REPLENISHMENT PLANNING SUMMARY")
        print("="*100)
        print(f"Total Orders Generated: {summary.total_orders_generated}")
        print(f"Total Order Cost: ${summary.total_order_cost:.2f}")
        print(f"Orders by Priority:")
        print(f"  - URGENT: {summary.orders_by_priority.get('URGENT', 0)}")
        print(f"  - HIGH: {summary.orders_by_priority.get('HIGH', 0)}")
        print(f"  - MEDIUM: {summary.orders_by_priority.get('MEDIUM', 0)}")
        print(f"  - LOW: {summary.orders_by_priority.get('LOW', 0)}")
        print(f"Average Lead Time: {summary.average_lead_time:.1f} days")
        
        if replenishment_results.get("azure_analysis"):
            print("\n" + "="*100)
            print("PHASE 4: AZURE OPENAI ANALYSIS")
            print("="*100)
            print(replenishment_results["azure_analysis"])
    
    logger.info("Complete workflow execution finished")


if __name__ == "__main__":
    main()
