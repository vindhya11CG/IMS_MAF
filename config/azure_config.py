from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv


# Load environment variables from .env
load_dotenv(override=True)



try:
    from openai import AzureOpenAI
except ImportError:  # pragma: no cover
    AzureOpenAI = None  # type: ignore[assignment]


@dataclass
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str = "2025-04-01-preview"
    temperature: float = 0.2
    max_tokens: int = 512  # used as max_completion_tokens

    def validate(self) -> None:
        if not self.endpoint:
            raise ValueError("Azure OpenAI endpoint is required.")
        if not self.api_key:
            raise ValueError("Azure OpenAI API key is required.")
        if not self.deployment:
            raise ValueError("Azure OpenAI deployment name is required.")

    @classmethod
    def from_env(cls) -> "AzureOpenAIConfig":
        return cls(
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
            temperature=float(os.getenv("AZURE_OPENAI_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("AZURE_OPENAI_MAX_TOKENS", "512")),
        )


class AzureOpenAIClient:
    def __init__(self, config: AzureOpenAIConfig) -> None:
        if AzureOpenAI is None:
            raise ImportError(
                "openai package is required to use AzureOpenAIClient. Install with: pip install openai"
            )

        config.validate()
        self.config = config

        self.client = AzureOpenAI(
            api_key=config.api_key,
            api_version=config.api_version,
            azure_endpoint=config.endpoint,
        )

    def create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Creates a chat completion using Azure OpenAI.
        Uses 'max_completion_tokens' (new API standard).
        """

        # Prepare parameters safely
        params: Dict[str, Any] = {
            "model": self.config.deployment,
            "messages": messages,
            "temperature": (
                temperature if temperature is not None else self.config.temperature
            ),
        }

        # ✅ FIX: Use new parameter name
        max_tokens_value = (
            max_tokens if max_tokens is not None else self.config.max_tokens
        )
        if max_tokens_value:
            params["max_completion_tokens"] = max_tokens_value

        response = self.client.chat.completions.create(**params)

        choice = response.choices[0]
        return (choice.message.content or "").strip()

    def build_system_message(self) -> Dict[str, str]:
        return {
            "role": "system",
            "content": (
                "You are an Inventory Monitoring Agent within a Microsoft Agent Framework setup. "
                "Provide concise recommendations and risk analysis from inventory data."
            ),
        }