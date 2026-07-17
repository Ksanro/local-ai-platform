"""Derived classes fixture for benchmark testing."""

from __future__ import annotations

from typing import Any

from tests.fixtures.repositories.inheritance.base import BaseHandler


class DerivedHandler(BaseHandler):
    """Concrete implementation of BaseHandler.

    Handles requests by processing them through registered
    event handlers or a default processing path.
    """

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        default_action: str = "process",
    ) -> None:
        """Initialize the derived handler.

        Args:
            name: The handler name.
            config: Optional configuration dictionary.
            default_action: The default action name.
        """
        super().__init__(name, config)
        self.default_action = default_action
        self._processed_count: int = 0

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an incoming request.

        Processes the request through the appropriate handler
        based on the action field.

        Args:
            request: The request dictionary.

        Returns:
            The response dictionary with status and data.
        """
        if not self.validate_request(request):
            return {"status": "error", "data": "Invalid request"}

        action = request.get("action", self.default_action)
        handler = self.get_handler(action)

        if handler is not None:
            result = handler(request)
            self._processed_count += 1
            return {"status": "ok", "data": result}

        return {"status": "default", "data": self._default_process(request)}

    def _default_process(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process a request using the default handler.

        Args:
            request: The request dictionary.

        Returns:
            The processed result.
        """
        return {"action": self.default_action, "request": request}

    def get_stats(self) -> dict[str, Any]:
        """Get handler statistics.

        Returns:
            A dictionary with handler statistics.
        """
        return {
            "name": self.name,
            "processed_count": self._processed_count,
            "handlers": list(self._handlers.keys()),
        }

    def reset_stats(self) -> None:
        """Reset the processed count."""
        self._processed_count = 0


class SecondaryHandler(BaseHandler):
    """Another concrete handler implementation.

    Focuses on batch processing of requests.
    """

    def __init__(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        batch_size: int = 10,
    ) -> None:
        """Initialize the secondary handler.

        Args:
            name: The handler name.
            config: Optional configuration dictionary.
            batch_size: Maximum batch size for processing.
        """
        super().__init__(name, config)
        self.batch_size = batch_size
        self._batch: list[dict[str, Any]] = []

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a request by adding to batch.

        Args:
            request: The request dictionary.

        Returns:
            The response with batch status.
        """
        self._batch.append(request)

        if len(self._batch) >= self.batch_size:
            return {"status": "batch_full", "data": self._flush_batch()}

        return {"status": "queued", "data": {"batch_size": len(self._batch)}}

    def _flush_batch(self) -> list[dict[str, Any]]:
        """Flush the current batch."""
        batch = list(self._batch)
        self._batch.clear()
        return batch

    def get_batch(self) -> list[dict[str, Any]]:
        """Get the current batch without clearing.

        Returns:
            A copy of the current batch.
        """
        return list(self._batch)