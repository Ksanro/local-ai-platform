"""Immutable capability result model.

Defines the output of a capability execution. This is the stable contract
between a capability and its consumers.

Constraints
-----------

- Immutable (frozen=True).
- No mutable state.
- No provider response (the capability stops after ProviderRequest creation).

Public API
----------

.. code-block:: python

    from packages.capabilities.models import CapabilityResult

    result = CapabilityResult(
        query="Explain ProviderFactory",
        intent="EXPLAIN",
        context_plan=plan,
        context_package=package,
        provider_request=request,
        selected_symbols=("ProviderFactory",),
        selected_modules=("packages/providers/factory.py",),
        estimated_tokens=256,
        execution_time_ms=42.5,
    )
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.context.context_package import ContextPackage
from packages.planning.plan import ContextPlan
from packages.serializers.models import ProviderRequest


@dataclass(frozen=True)
class CapabilityResult:
    """Immutable result of a capability execution.

    Attributes:
        query: The original user query string.
        intent: Detected intent from the query (e.g. "EXPLAIN").
        context_plan: The planning result that guided the execution.
        context_package: The assembled context package for the request.
        provider_request: The serialized provider request.
        selected_symbols: Tuple of selected symbol qualified names.
        selected_modules: Tuple of selected module file paths.
        estimated_tokens: Estimated token count for the context.
        execution_time_ms: Total execution time in milliseconds.
    """

    query: str
    intent: str
    context_plan: ContextPlan
    context_package: ContextPackage
    provider_request: ProviderRequest
    selected_symbols: tuple[str, ...] = ()
    selected_modules: tuple[str, ...] = ()
    estimated_tokens: int = 0
    execution_time_ms: float = 0.0
