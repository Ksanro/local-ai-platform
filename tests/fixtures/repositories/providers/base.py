"""Base provider fixture for benchmark testing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProviderBase(ABC):
    """Abstract base class for providers.

    All concrete providers must implement these methods.
    """

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        """Initialize the provider.

        Args:
            name: The provider name.
            config: Optional configuration dictionary.
        """
        self.name = name
        self.config = config or {}
        self._initialized = False

    @abstractmethod
    async def execute(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        """Execute the provider with the given messages.

        Args:
            messages: List of message dictionaries.
            **kwargs: Additional provider-specific parameters.

        Returns:
            The provider response.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is healthy.

        Returns:
            True if the provider is healthy, False otherwise.
        """
        ...

    def initialize(self) -> None:
        """Initialize the provider.

        Sets the internal initialized flag. Override for custom setup.
        """
        self._initialized = True

    def is_initialized(self) -> bool:
        """Check if the provider is initialized.

        Returns:
            True if initialized, False otherwise.
        """
        return self._initialized

    def get_config(self, key: str) -> Any:
        """Get a configuration value.

        Args:
            key: The configuration key.

        Returns:
            The configuration value, or None if not found.
        """
        return self.config.get(key)

    def __repr__(self) -> str:
        """Return a string representation of the provider."""
        return f"{self.__class__.__name__}(name={self.name!r})"
