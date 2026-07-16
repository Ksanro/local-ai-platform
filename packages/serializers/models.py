"""Provider request model.

Defines the typed payload that serializers produce and providers consume.
This is the boundary between the Serialization Layer and the Provider Layer.

Architecture
------------

Serializer produces ProviderRequest.
Provider consumes ProviderRequest.

Providers never consume ContextPackage.
Serializers never produce ProviderRequest with transport concerns.

ProviderRequest is provider-agnostic in structure but provider-specific
in content. Each serializer fills in the fields appropriate for its
target provider.

Constraints
-----------

- No HTTP headers (transport concern).
- No authentication data (provider concern).
- No retry configuration (provider concern).
- No streaming configuration (provider concern).

Public API
----------

.. code-block:: python

    request = ProviderRequest(
        provider_type=ProviderType.openai,
        messages=[...],
        model="gpt-4",
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.serializers.types import ProviderType


@dataclass(frozen=True)
class ProviderRequest:
    """A provider request payload produced by a serializer.

    This is the output of the Serialization Layer and the input
    to the Provider Layer. It contains only the data needed to
    format a request — no transport, auth, or execution concerns.

    Attributes:
        provider_type: The target provider type this request targets.
        messages: Formatted messages ready for the provider API.
        model: Model identifier for the provider.
        kwargs: Additional provider-specific parameters (temperature,
            max_tokens, tools, etc.).
    """

    provider_type: ProviderType
    messages: list[dict[str, Any]]
    model: str = "default"
    kwargs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a flat dict for provider consumption.

        Combines messages, model, and kwargs into a single dict
        that providers can forward directly to their API.

        Returns:
            A dict with keys ``messages``, ``model``, and all
            additional keys from ``kwargs``.
        """
        result: dict[str, Any] = {
            "messages": self.messages,
            "model": self.model,
        }
        result.update(self.kwargs)
        return result
