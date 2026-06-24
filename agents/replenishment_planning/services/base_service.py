"""Base service class for replenishment planning services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ReplenishmentService(ABC):
    """Base class for replenishment planning services."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("ReplenishmentService subclasses must implement execute().")
