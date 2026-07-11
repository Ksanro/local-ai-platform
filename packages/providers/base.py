"""Abstract provider base class.

Defines the interface that all AI provider implementations must satisfy.
Providers are responsible for health checks, model listing, and chat
completion requests.
"""

from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    """Abstract provider interface.

    All AI provider implementations (vLLM, OpenAI, etc.) must inherit
    from this class and implement ``health``, ``chat``, and ``models``.
    """

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """Check provider health status.

        Returns a dict with at least a ``healthy`` key (bool) and
        optionally a ``status`` key describing the health state.
        """

    @abstractmethod
    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a chat completion request.

        Forwards the chat payload to the provider and returns the
        parsed response as a dict. When ``stream=True`` is passed,
        the implementation may return a dict with ``generator`` and
        ``media_type`` keys instead of a direct response.
        """

    @abstractmethod
    async def models(self) -> list[str]:
        """List available provider models.

        Returns a list of model identifier strings.
        """
