# Inventory Monitoring Agent Services

This project contains initial service scaffolding for the inventory monitoring agent.

## What is included

- `inventory_agent/data_loader.py`: Loads inventory-related CSV exports.
- `inventory_agent/inventory_calculation_service.py`: Computes current stock using inventory snapshots.
- `inventory_agent/inventory_risk_monitoring_service.py`: Evaluates stock risk based on reorder points, safety stock, and projected demand.
- `inventory_agent/main.py`: Starter execution script demonstrating service output and optional Azure OpenAI analysis.
- `inventory_agent/azure_openai_client.py`: Azure OpenAI wrapper for the provided Azure resource.
- `inventory_agent/agent_coordinator.py`: Inventory Monitoring Agent orchestration that combines the services and connects to Azure OpenAI when available.

## Notes

- The service design follows the main workflow definition: inventory calculation first, then risk monitoring.
- Azure OpenAI / Microsoft Agent Framework integration is now wired into the package via `AzureOpenAIClient` and `InventoryMonitoringAgent`.
- `inventory_agent/main.py` will run local calculation and risk assessment and attempt Azure OpenAI analysis if the SDK is installed and environment variables are configured.
- CSV sources are read from `csv_exports/` using the provided export structure.

## Configuration

Copy `.env.example` to `.env` and populate the Azure values, or set the following environment variables:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`

If you use `.env`, the project startup script will automatically load it when `python-dotenv` is installed.

## Install Dependencies

From the project root:

```powershell
pip install -r requirements.txt
```

## Test the Project

1. Activate your virtual environment.
2. Install dependencies.
3. Create a `.env` from `.env.example` or set the required environment variables.
4. Run:

```powershell
python -m inventory_agent.main
```

This will execute the inventory calculation and risk monitoring services locally. If Azure OpenAI is configured, it will also attempt an Azure chat completion with `gpt-5.4-mini`.
