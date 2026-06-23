from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool

from dotenv import load_dotenv
import os

load_dotenv()

from config import AzureOpenAIClient, AzureOpenAIConfig
from utils.logging_setup import setup_logging
from agents.inventory_monitoring.agent import InventoryMonitoringAgent

logger = logging.getLogger(__name__)

app = FastAPI(title="IMS Inventory Monitoring API")


@app.on_event("startup")
def startup_event() -> None:
    """Application startup: configure logging and prepare agent factory."""
    setup_logging(logging.INFO, log_file="logs/inventory_monitoring_api.log")
    logger.info("IMS API starting up")


def _create_agent() -> InventoryMonitoringAgent:
    """Create an InventoryMonitoringAgent wired with Azure client if available."""
    openai_client = None
    try:
        config = AzureOpenAIConfig.from_env()
        openai_client = AzureOpenAIClient(config)
        logger.info("Azure OpenAI client configured for API")
    except Exception as e:  # pragma: no cover
        logger.warning(f"Azure OpenAI not configured for API: {e}")

    agent = InventoryMonitoringAgent(openai_client=openai_client)
    return agent


@app.get("/run-agent")
async def run_agent() -> Dict[str, Any]:
    """Trigger the InventoryMonitoringAgent and return a concise JSON summary.

    This endpoint runs the agent synchronously in a threadpool to avoid blocking the event loop.
    """
    agent = _create_agent()

    try:
        result = await run_in_threadpool(agent.execute)
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    # Build a JSON-safe response
    response = {
        "summary": result.get("summary"),
        "azure_analysis": result.get("azure_analysis"),
        "counts": {
            "snapshots": len(result.get("phase1_snapshots", [])),
            "calculations": len(result.get("calculations", [])),
            "assessments": len(result.get("assessments", [])),
        },
    }
    return response
