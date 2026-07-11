# Implementation Plan: FastAPI Endpoints for Multi-Agent Setup

We are going to build out the modular FastAPI architecture to expose the Multi-Agent workflow to the frontend. Since the project uses CSV files instead of a database, we must use an in-memory state manager to cache the agent results and serve them quickly to the frontend.

## User Review Required
> [!IMPORTANT]
> Because there is no persistent database, the `GET` endpoints (like `/risks` or `/orders`) will return empty arrays **until** the user (or frontend) triggers the `POST /api/v1/agent/run-full` endpoint at least once after the server starts. We will build a state manager to hold the agent's output in memory.

## Proposed Changes

### 1. Global State & Dependencies (`api/core/`)
To avoid loading CSVs on every request and to store the agent's results:
#### [NEW] `api/core/state.py`
- Create a global `AppState` class that holds:
  - `status`: "IDLE" or "RUNNING"
  - `last_run`: Timestamp of the last execution
  - `results`: The dictionary returned by `AgentOrchestrator.execute()`
  - `raw_data`: Cached output of the `CsvInventoryDataLoader`

#### [NEW] `api/core/dependencies.py`
- Create dependency injection functions `get_state()` and `get_csv_loader()` so the routers can access the data cleanly.

---

### 2. The Routers (`api/v1/routers/`)

#### [NEW] `api/v1/routers/agent.py`
The control panel for the agents.
- `POST /run-full`: Triggers `AgentOrchestrator` in a background thread to prevent blocking the API. Updates the global state when finished.
- `GET /status`: Returns `{"status": "RUNNING" | "IDLE"}`.
- `GET /last-run`: Returns the timestamp and workflow summary.
- `GET /analysis/risks`: Returns the Azure OpenAI NLP summary for Phase 1-3.
- `GET /analysis/replenishment`: Returns the Azure OpenAI NLP summary for Phase 4.

#### [NEW] `api/v1/routers/inventory.py`
The raw data inputs (Agent 1 Input).
- `GET /snapshots`: Returns `state.raw_data.snapshots`.
- `GET /positions`: Returns `state.raw_data.positions`.

#### [NEW] `api/v1/routers/risks.py`
The handoff state (Agent 1 Output ➡️ Agent 2 Input).
- `GET /`: Returns all risk assessments from `state.results`.
- `GET /detected`: Returns only the assessments where `risk_detected=True`.

#### [NEW] `api/v1/routers/orders.py`
The final results (Agent 2 Output).
- `GET /`: Returns the generated replenishment orders from `state.results`.
- `GET /summary`: Returns the replenishment summary (costs, priorities, average lead time).

---

### 3. Wiring It All Together

#### [NEW] `api/v1/api.py`
- The central `APIRouter` that aggregates the 4 routers above with their respective prefixes (`/agent`, `/inventory`, `/risks`, `/orders`).

#### [MODIFY] `main.py`
- We will update the root `main.py` (or create a new `api/main.py` if preferred, but usually `main.py` at the root is good) to instantiate the FastAPI app, include the `api_router`, and use the `lifespan` event to pre-load the CSV data into the `AppState` when the server starts.

## Verification Plan
1. Start the FastAPI server using `uvicorn main:app --reload`.
2. Verify that `GET /api/v1/agent/status` returns "IDLE".
3. Trigger `POST /api/v1/agent/run-full` and verify it runs asynchronously.
4. Call `GET /api/v1/risks/detected` and `GET /api/v1/orders` to ensure they return the populated data correctly.
