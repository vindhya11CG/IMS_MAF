"""
Consolidated: AzureConfigService + ExplanationService
(previously azure_config_service.py + explanation_service.py)

Behavior is unchanged from the original code - only file location changed.
ExplanationService already degrades gracefully to a canned explanation if
Azure OpenAI isn't reachable/configured, so the agent works fully offline.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class AzureConfigService:
    """Builds the Azure OpenAI client. The openai package and/or valid
    Azure credentials may not always be present. Rather than let a hard
    ImportError/credential error take down the whole agent import chain,
    failures are captured on the instance and surfaced lazily so
    ExplanationService can fall back gracefully instead of crashing."""

    def __init__(self):
        self.client = None
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self.temperature = float(os.getenv("AZURE_OPENAI_TEMPERATURE", 0.2))
        self.max_tokens = int(os.getenv("AZURE_OPENAI_MAX_TOKENS", 512))
        self.init_error = None

        try:
            from openai import AzureOpenAI  # optional dependency

            self.client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            )
        except Exception as e:
            self.init_error = e


class ExplanationService:

    def __init__(self):
        cfg = AzureConfigService()
        self.client = cfg.client
        self.model = cfg.deployment

    def execute(self, sku, forecast, confidence):
        if self.client is None:
            return self._fallback(forecast, confidence)
        try:
            r = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Explain inventory forecast.",
                    },
                    {
                        "role": "user",
                        "content": f"""
Product:
{sku}

Forecast:
{forecast}

Confidence:
{confidence}
""",
                    },
                ],
            )
            return r.choices[0].message.content
        except Exception:
            return self._fallback(forecast, confidence)

    @staticmethod
    def _fallback(forecast, confidence):
        return f"""
Forecast:

{forecast}

Confidence:

{confidence}

Inventory planning recommended.
"""
