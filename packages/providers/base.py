"""Abstract provider base class."""

from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    """Abstract provider interface."""

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """Check provider health status."""

    @abstractmethod
    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a chat completion request."""

    @abstractmethod
    async def models(self) -> list[str]:
        """List available provider models."""
