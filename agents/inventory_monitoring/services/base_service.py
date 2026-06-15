"""Base service class for inventory monitoring services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AgentService(ABC):
    """Base class for agent services in the Microsoft Agent Framework architecture."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("AgentService subclasses must implement execute().")
