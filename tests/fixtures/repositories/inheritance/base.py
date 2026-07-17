"""Base classes fixture for benchmark testing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseHandler(ABC):
    """Abstract base handler for processing requests.

    All concrete handlers must implement handle_request.
    """

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        """Initialize the base handler.

        Args:
            name: The handler name.
            config: Optional configuration dictionary.
        """
        self.name = name
        self.config = config or {}
        self._handlers: dict[str, Any] = {}

    @abstractmethod
    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an incoming request.

        Args:
            request: The request dictionary.

        Returns:
            The response dictionary.
        """
        ...

    def register_handler(self, event: str, handler: Any) -> None:
        """Register an event handler.

        Args:
            event: The event name.
            handler: The handler function or callable.
        """
        self._handlers[event] = handler

    def get_handler(self, event: str) -> Any | None:
        """Get a registered handler by event name.

        Args:
            event: The event name.

        Returns:
            The handler, or None if not found.
        """
        return self._handlers.get(event)

    def has_handler(self, event: str) -> bool:
        """Check if a handler is registered for an event.

        Args:
            event: The event name.

        Returns:
            True if handler exists, False otherwise.
        """
        return event in self._handlers

    def validate_request(self, request: dict[str, Any]) -> bool:
        """Validate an incoming request.

        Args:
            request: The request dictionary.

        Returns:
            True if valid, False otherwise.
        """
        if not isinstance(request, dict):
            return False
        return "action" in request