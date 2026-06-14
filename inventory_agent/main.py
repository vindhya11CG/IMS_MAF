from inventory_agent import AzureOpenAIConfig, AzureOpenAIClient, InventoryMonitoringAgent

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    config = AzureOpenAIConfig.from_env()
    try:
        openai_client = AzureOpenAIClient(config)
    except ImportError:
        openai_client = None
    except ValueError as error:
        print(f"Azure OpenAI configuration warning: {error}")
        openai_client = None

    agent = InventoryMonitoringAgent(openai_client=openai_client)
    output = agent.execute()

    print("Inventory Monitoring Agent Summary")
    print(output["summary"])
    if output["azure_analysis"]:
        print("\nAzure OpenAI Analysis")
        print(output["azure_analysis"])
    else:
        print("\nAzure OpenAI client not configured or not available. Skipping Azure analysis.")


if __name__ == "__main__":
    main()
