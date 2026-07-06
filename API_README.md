FastAPI API for Inventory Monitoring Agent
=========================================

Run the Inventory Monitoring Agent via a lightweight FastAPI endpoint for testing.

Install dependencies (create and activate your virtual env first):

```powershell
pip install -r requirements.txt
```

Run the API server:

```powershell
uvicorn api.app:app --reload --port 8000
```

Endpoint:
- `GET /run-agent` — runs the `InventoryMonitoringAgent` and returns a concise JSON summary

Notes:
- Keep your `.env` configured for Azure OpenAI if you want the Azure analysis step.
- Do not commit `.env` to source control.
