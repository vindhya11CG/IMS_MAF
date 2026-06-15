"""Main entry point for the Inventory Management System."""

import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agents.inventory_monitoring import InventoryMonitoringAgent
from config import AzureOpenAIClient, AzureOpenAIConfig
from utils import setup_logging

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

logger = logging.getLogger(__name__)


def main() -> None:
    """Execute the inventory monitoring workflow."""
    # Setup logging
    setup_logging(logging.INFO, log_file="logs/inventory_monitoring.log")
    logger.info("="*80)
    logger.info("Starting Inventory Management System - Inventory Monitoring Agent")
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

    agent = InventoryMonitoringAgent(openai_client=openai_client)
    output = agent.execute()

    print("\n" + "="*80)
    print("INVENTORY MONITORING AGENT SUMMARY")
    print("="*80)
    print(output["summary"])
    
    if output["azure_analysis"]:
        print("\n" + "="*80)
        print("AZURE OPENAI ANALYSIS")
        print("="*80)
        print(output["azure_analysis"])
    else:
        print("\nAzure OpenAI client not configured or not available. Skipping Azure analysis.")
    
    logger.info("Inventory Monitoring Agent execution completed")


if __name__ == "__main__":
    main()
