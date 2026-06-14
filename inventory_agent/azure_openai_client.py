from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from azure.ai.openai import OpenAIClient
    from azure.core.credentials import AzureKeyCredential
except ImportError:  # pragma: no cover
    OpenAIClient = None  # type: ignore[assignment]
    AzureKeyCredential = None  # type: ignore[assignment]


@dataclass
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str = "2025-04-01-preview"
    temperature: float = 0.2
    max_tokens: int = 512

    def validate(self) -> None:
        if not self.endpoint:
            raise ValueError("Azure OpenAI endpoint is required.")
        if not self.api_key:
            raise ValueError("Azure OpenAI API key is required.")
        if not self.deployment:
            raise ValueError("Azure OpenAI deployment name is required.")

    @classmethod
    def from_env(cls) -> AzureOpenAIConfig:
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
        if OpenAIClient is None or AzureKeyCredential is None:
            raise ImportError(
                "azure-ai-openai and azure-core are required to use AzureOpenAIClient."
            )
        config.validate()
        self.config = config
        self.client = OpenAIClient(
            endpoint=config.endpoint,
            credential=AzureKeyCredential(config.api_key),
        )

    def create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        response = self.client.get_chat_completions(
            deployment_name=self.config.deployment,
            messages=messages,
            temperature=temperature if temperature is not None else self.config.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.config.max_tokens,
        )
        choice = response.choices[0]
        return choice.message.content.strip()

    def build_system_message(self) -> Dict[str, str]:
        return {
            "role": "system",
            "content": (
                "You are an Inventory Monitoring Agent within a Microsoft Agent Framework setup. "
                "Provide concise recommendations and risk analysis from inventory data."
            ),
        }
