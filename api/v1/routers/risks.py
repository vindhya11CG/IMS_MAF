from fastapi import APIRouter, Depends
from api.core.state import AppState
from api.core.dependencies import get_app_state

router = APIRouter()

@router.get("/")
async def get_all_risks(state: AppState = Depends(get_app_state)):
    """Get all computed risk assessments (Agent 1 Output)."""
    phase_1_3 = state.results.get("phase_1_3_results", {})
    return phase_1_3.get("assessments", [])

@router.get("/detected")
async def get_detected_risks(state: AppState = Depends(get_app_state)):
    """Get only the items flagged as risky (Agent 2 Input)."""
    phase_1_3 = state.results.get("phase_1_3_results", {})
    assessments = phase_1_3.get("assessments", [])
    
    # Safely filter for risk_detected == True (handling both objects and dicts)
    detected = []
    for a in assessments:
        if hasattr(a, 'risk_detected') and getattr(a, 'risk_detected'):
            detected.append(a)
        elif isinstance(a, dict) and a.get('risk_detected'):
            detected.append(a)
            
    return detected
