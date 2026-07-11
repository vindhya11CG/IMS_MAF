import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from api.core.state import AppState
from api.core.dependencies import get_app_state
from agent_orchestrator import AgentOrchestrator
from config import AzureOpenAIClient, AzureOpenAIConfig

logger = logging.getLogger(__name__)
router = APIRouter()

def _create_agent_orchestrator() -> AgentOrchestrator:
    openai_client = None
    try:
        config = AzureOpenAIConfig.from_env()
        openai_client = AzureOpenAIClient(config)
    except Exception as e:
        logger.warning(f"Azure OpenAI not configured: {e}")
    return AgentOrchestrator(openai_client=openai_client)

def run_agent_background(state: AppState):
    """Background task to run the agent pipeline."""
    try:
        orchestrator = _create_agent_orchestrator()
        results = orchestrator.execute()
        state.set_results(results)
        logger.info("Agent pipeline execution completed in background.")
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        state.update_status("ERROR")

@router.post("/run-full")
async def run_agent_full(
    background_tasks: BackgroundTasks,
    state: AppState = Depends(get_app_state)
):
    """Kick off the full multi-agent pipeline (Phases 1-4) in the background."""
    if state.status == "RUNNING":
        raise HTTPException(status_code=400, detail="Agent is already running.")
    
    state.update_status("RUNNING")
    background_tasks.add_task(run_agent_background, state)
    
    return {"message": "Agent pipeline started successfully."}

@router.get("/status")
async def get_agent_status(state: AppState = Depends(get_app_state)):
    """Check if the agent is currently running."""
    return {"status": state.status}

@router.get("/last-run")
async def get_last_run(state: AppState = Depends(get_app_state)):
    """Get the timestamp and summary of the last execution."""
    if not state.last_run:
        return {"message": "Agent has not been run yet."}
    
    return {
        "last_run": state.last_run.isoformat(),
        "summary": state.results.get("summary", "")
    }

@router.get("/analysis/risks")
async def get_risk_analysis(state: AppState = Depends(get_app_state)):
    """Get Azure OpenAI analysis for Phase 1-3 risks."""
    phase_1_3 = state.results.get("phase_1_3_results", {})
    return {"analysis": phase_1_3.get("azure_analysis", None)}

@router.get("/analysis/replenishment")
async def get_replenishment_analysis(state: AppState = Depends(get_app_state)):
    """Get Azure OpenAI analysis for Phase 4 replenishment orders."""
    phase_4 = state.results.get("phase_4_results", {})
    return {"analysis": phase_4.get("azure_analysis", None)}
