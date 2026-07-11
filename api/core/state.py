from typing import Any, Dict, Optional
from datetime import datetime
import threading


class AppState:
    """In-memory state manager to hold CSV data, Agent results, and model status."""

    def __init__(self) -> None:
        self.status: str = "IDLE"
        self.last_run: Optional[datetime] = None
        self.results: Dict[str, Any] = {}
        self.raw_data: Dict[str, Any] = {
            "snapshots": [],
            "positions": [],
        }

        # --- Demand-forecasting model tracking (set during startup) ---
        self.model_loaded: bool = False
        self.model_loaded_at: Optional[datetime] = None
        self.startup_time: datetime = datetime.now()

        self.lock = threading.Lock()

    def update_status(self, new_status: str) -> None:
        with self.lock:
            self.status = new_status

    def set_results(self, results: Dict[str, Any]) -> None:
        with self.lock:
            self.results = results
            self.last_run = datetime.now()
            self.status = "IDLE"

    def mark_model_loaded(self) -> None:
        """Called once during startup after the forecasting model is loaded."""
        with self.lock:
            self.model_loaded = True
            self.model_loaded_at = datetime.now()


# Global singleton instance
state = AppState()

