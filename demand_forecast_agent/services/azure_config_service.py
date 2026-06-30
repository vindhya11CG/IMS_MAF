import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()


class AzureConfigService:

    def __init__(self):

        self.client = AzureOpenAI(
            api_key=os.getenv(
                "AZURE_OPENAI_API_KEY"
            ),
            api_version=os.getenv(
                "AZURE_OPENAI_API_VERSION"
            ),
            azure_endpoint=os.getenv(
                "AZURE_OPENAI_ENDPOINT"
            )
        )

        self.deployment = os.getenv(
            "AZURE_OPENAI_DEPLOYMENT"
        )

        self.temperature = float(
            os.getenv(
                "AZURE_OPENAI_TEMPERATURE",
                0.2
            )
        )

        self.max_tokens = int(
            os.getenv(
                "AZURE_OPENAI_MAX_TOKENS",
                512
            )
        )