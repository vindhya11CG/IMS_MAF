"""Base service class for supplier selection services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SupplierSelectionService(ABC):
    """Base class for supplier selection services."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("SupplierSelectionService subclasses must implement execute().")
