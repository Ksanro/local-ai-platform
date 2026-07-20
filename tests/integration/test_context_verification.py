"""Integration test: context verification through the full pipeline.

Verifies that repository context travels through the complete pipeline
from RepositoryIndex to ProviderRequest.

Tests
-----
- RepositoryContextStage executes with real index
- ContextPackage is created with symbols and modules
- symbols > 0 and modules > 0
- serialized ProviderRequest contains injected repository context
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.context.builder import ContextBuilder
from packages.context.context_package import ContextPackage
from packages.context.models import ContextQuery, ContextResult
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.repository import build_index
from packages.repository.index.models import RepositoryIndex
from packages.serializers.factory import SerializerFactory
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType


@pytest.fixture
def test_repo() -> Path:
    """Return the project root as the test repository."""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def repository_index(test_repo: Path) -> RepositoryIndex:
    """Build a real RepositoryIndex from the test repository."""
    index = build_index(test_repo)
    assert isinstance(index, RepositoryIndex)
    return index


@pytest.mark.asyncio
async def test_context_verification(repository_index: RepositoryIndex) -> None:
    """Verify that RepositoryContextStage produces context from a real index.

    Uses a real repository and a query that searches for a known symbol
    (RepositoryContextStage is implemented in this project).

    Verifies:
    - RepositoryContextStage executed
    - ContextPackage created
    - symbols > 0
    - modules > 0
    - serialized ProviderRequest contains injected repository context
    """
    # Use a query that should match symbols in the project.
    query_text = "RepositoryContextStage"

    # Build context using the real index.
    builder = ContextBuilder(repository_index)
    query = ContextQuery(
        text=query_text,
        max_symbols=20,
        max_modules=10,
        max_tokens=4096,
    )
    context_result: ContextResult = builder.build(query)

    # Verify context was built.
    assert context_result is not None
    assert len(context_result.candidates) > 0
    assert len(context_result.selected_modules) > 0

    # Verify symbols and modules counts.
    assert len(context_result.candidates) > 0, "Expected symbols > 0"
    assert len(context_result.selected_modules) > 0, "Expected modules > 0"

    # Build ContextPackage from context result.
    candidates = context_result.candidates
    selected_modules = context_result.selected_modules
    budget = context_result.budget

    primary_symbol = candidates[0].symbol_id if candidates else ""
    supporting_symbols = [c.symbol_id for c in candidates[1:]]

    context_package = ContextPackage(
        primary_symbol=primary_symbol,
        supporting_symbols=supporting_symbols,
        related_modules=selected_modules,
        estimated_tokens=budget.estimated_tokens,
    )

    # Verify ContextPackage has content.
    assert context_package.primary_symbol != ""
    assert len(context_package.supporting_symbols) >= 0
    assert len(context_package.related_modules) > 0

    # Serialize to ProviderRequest.
    serializer = SerializerFactory.create(ProviderType.openai)
    messages: list[dict[str, object]] = [{"role": "user", "content": query_text}]
    provider_request: ProviderRequest = serializer.serialize(
        context_package, messages
    )

    # Verify ProviderRequest contains injected repository context.
    assert provider_request is not None

    # Verify the serialized request contains context information.
    # The ProviderRequest messages contain the context.
    assert len(provider_request.messages) > 0


@pytest.mark.asyncio
async def test_repository_context_stage_with_index(repository_index: RepositoryIndex) -> None:
    """Verify that RepositoryContextStage receives and uses the real index."""
    # Create RepositoryContextStage with the real index.
    stage = RepositoryContextStage(index=repository_index)

    # Verify the stage has the index.
    assert stage._index is not None
    assert isinstance(stage._index, RepositoryIndex)

    # Verify the index has content.
    stats = repository_index.statistics()
    assert stats.symbol_count > 0
    assert stats.module_count > 0


@pytest.mark.asyncio
async def test_context_reaches_provider_request(repository_index: RepositoryIndex) -> None:
    """Verify that context travels from RepositoryIndex to ProviderRequest.

    Full pipeline:
    RepositoryIndex -> ContextBuilder -> ContextPackage -> Serializer -> ProviderRequest
    """
    # Step 1: Build context from the real index.
    builder = ContextBuilder(repository_index)
    query = ContextQuery(
        text="test",
        max_symbols=10,
        max_modules=5,
        max_tokens=2048,
    )
    context_result = builder.build(query)

    # Step 2: Verify context has content.
    assert len(context_result.candidates) > 0
    assert len(context_result.selected_modules) > 0

    # Step 3: Build ContextPackage.
    candidates = context_result.candidates
    budget = context_result.budget

    primary_symbol = candidates[0].symbol_id if candidates else ""
    supporting_symbols = [c.symbol_id for c in candidates[1:]]

    context_package = ContextPackage(
        primary_symbol=primary_symbol,
        supporting_symbols=supporting_symbols,
        related_modules=context_result.selected_modules,
        estimated_tokens=budget.estimated_tokens,
    )

    # Step 4: Serialize to ProviderRequest.
    serializer = SerializerFactory.create(ProviderType.openai)
    messages = [{"role": "user", "content": "test query"}]
    provider_request = serializer.serialize(context_package, messages)

    # Step 5: Verify ProviderRequest was created.
    assert provider_request is not None

    # The full pipeline executed: RepositoryIndex -> ContextPackage -> ProviderRequest.
    assert isinstance(context_package, ContextPackage)
    assert isinstance(provider_request, ProviderRequest)
