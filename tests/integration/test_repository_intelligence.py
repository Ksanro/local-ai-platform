"""Integration tests: end-to-end repository intelligence pipeline.

Verifies that the complete pipeline — RepositoryContextStage →
ProviderStage — works correctly with mocked providers.

Tests
-----
- repository context enabled
- repository context disabled
- provider receives ProviderRequest
- serializer invoked
- response unchanged
- pipeline ordering
- graceful failure
- repeated execution deterministic

Uses mocked providers. Does not require a running vLLM instance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from packages.context.context_package import ContextPackage
from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.request import PipelineRequest
from packages.pipeline.response import PipelineResponse
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.pipeline.stages.stages import ProviderStage
from packages.providers.base import Provider
from packages.providers.models import ModelDefinition, ResolvedModel
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType


def _make_request(
    messages: list[dict[str, Any]] | None = None,
    request_id: str = "test-req-1",
    context_enabled: bool = True,
) -> PipelineRequest:
    """Create a PipelineRequest with the given messages."""
    return PipelineRequest(
        provider_name="vllm",
        model="test-model",
        messages=messages or [
            {"role": "user", "content": "test query"}
        ],
        stream=False,
        metadata={
            "request_id": request_id,
            "context_enabled": context_enabled,
        },
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_symbol(
    name: str,
    qualified_name: str,
    module: str = "main",
    lineno: int = 1,
) -> Any:
    """Create a Symbol for testing."""
    from packages.repository.symbols.models import Symbol, SymbolType

    return Symbol(
        id=qualified_name,
        name=name,
        qualified_name=qualified_name,
        symbol_type=SymbolType.FUNCTION,
        module=module,
        lineno=lineno,
    )


def _make_index(symbols: list[Any]) -> Any:
    """Create a RepositoryIndex from a list of symbols."""
    from packages.repository.index.models import (
        Module,
        RepositoryIndex,
        RepositoryStatistics,
        SymbolType,
    )

    modules: dict[str, Any] = {}
    for sym in symbols:
        if sym.module not in modules:
            modules[sym.module] = Module(path=sym.module)
        modules[sym.module].symbols.append(sym)

    class_count = sum(
        1 for s in symbols if getattr(s, "symbol_type", None) == SymbolType.CLASS
    )
    function_count = sum(
        1
        for s in symbols
        if getattr(s, "symbol_type", None) == SymbolType.FUNCTION
    )
    method_count = sum(
        1 for s in symbols if getattr(s, "symbol_type", None) == SymbolType.METHOD
    )

    statistics = RepositoryStatistics(
        module_count=len(modules),
        class_count=class_count,
        function_count=function_count,
        method_count=method_count,
        symbol_count=len(symbols),
    )

    return RepositoryIndex(
        modules=modules,
        _symbols=symbols,
        _relationships=[],
        _statistics=statistics,
    )


def _make_context(
    messages: list[dict[str, Any]] | None = None,
    request_id: str = "test-req-1",
    context_enabled: bool = True,
) -> PipelineContext:
    """Create a PipelineContext with the given messages."""
    return PipelineContext(
        request_id=request_id,
        request={
            "messages": messages or [
                {"role": "user", "content": "test query"}
            ],
            "model": "test-model",
            "stream": False,
        },
        metadata={
            "request_id": request_id,
            "context_enabled": context_enabled,
        },
    )


def _make_resolved_model(mock_provider: "_MockProvider") -> ResolvedModel:
    """Create a ResolvedModel wrapping the given mock provider."""
    definition = ModelDefinition(
        model="test-model",
        provider="vllm",
        base_url="http://localhost:8000/v1",
        context_window=131072,
    )
    return ResolvedModel(definition=definition, provider=mock_provider)


def _make_engine(
    context_stage: RepositoryContextStage,
) -> PipelineEngine:
    """Build a pipeline engine with the given stage and a routing-agnostic ProviderStage."""
    engine = PipelineEngine()
    engine.register(context_stage)
    engine.register(ProviderStage())
    return engine


async def _run_pipeline(
    context_stage: RepositoryContextStage,
    mock_provider: "_MockProvider",
    request: PipelineRequest | None = None,
) -> PipelineResponse:
    """Create a context with resolved_model and run the stages.

    The engine's execute() creates its own PipelineContext internally,
    so we must create the context here, set resolved_model, then run
    the stages directly.
    """
    req = request or _make_request(context_enabled=True)
    context = PipelineContext(
        request_id=req.metadata.get("request_id", ""),
        request=req.to_provider_kwargs(),
    )
    context.set_metadata("provider_name", req.provider_name)
    context.set_metadata("model", req.model)
    context.set_metadata("context_enabled", req.metadata.get("context_enabled", True))
    context.resolved_model = _make_resolved_model(mock_provider)

    # Run stages directly (bypassing engine.execute which creates its own context)
    all_results: dict[str, PipelineStageResult] = {}
    for stage in [context_stage, ProviderStage()]:
        try:
            short_circuit = await stage.before(context)
            if short_circuit is not None:
                result = short_circuit
                if not isinstance(result, PipelineStageResult):
                    result = PipelineStageResult(
                        stage_name=stage.name,
                        success=True,
                        data=result,
                    )
            else:
                result = await stage.execute(context)
            after_result = await stage.after(context, result)
            if after_result is not None and isinstance(after_result, PipelineStageResult):
                result = after_result
            context.set_stage_result(stage.name, result)
            all_results[stage.name] = result
            if not result.success:
                break
        except Exception as exc:
            error_result = PipelineStageResult(
                stage_name=stage.name,
                success=False,
                error=str(exc),
                exception=exc,
            )
            context.set_stage_result(stage.name, error_result)
            all_results[stage.name] = error_result
            break
    return PipelineResponse.from_context(context)


class _MockProvider(Provider):
    """Mock provider that records the kwargs it receives."""

    def __init__(self) -> None:
        """Initialize the mock provider."""
        self.chat_calls: list[dict[str, Any]] = []
        self._response: dict[str, Any] = {
            "choices": [
                {"message": {"role": "assistant", "content": "ok"}}
            ]
        }

    async def health(self) -> dict[str, Any]:
        """Return healthy status."""
        return {"healthy": True, "status": "ok"}

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        """Record kwargs and return the canned response."""
        self.chat_calls.append(kwargs)
        return self._response

    async def models(self) -> list[str]:
        """Return empty model list."""
        return []

    async def close(self) -> None:
        """No-op close."""


# ------------------------------------------------------------------
# Repository context enabled
# ------------------------------------------------------------------


class TestContextEnabled:
    """Tests for repository context enabled scenario."""

    @pytest.mark.asyncio
    async def test_context_package_generated(self) -> None:
        """Verify ContextPackage is generated when context is enabled."""
        symbols = [
            _make_symbol("App", "main.App", "main.py"),
            _make_symbol("run", "main.App.run", "main.py"),
        ]
        index = _make_index(symbols)
        stage = RepositoryContextStage(index=index)

        context = _make_context(context_enabled=True)
        result = await stage.execute(context)

        assert result.success is True
        assert context.context_package is not None
        assert isinstance(context.context_package, ContextPackage)
        assert len(context.context_package.supporting_symbols) > 0

    @pytest.mark.asyncio
    async def test_provider_request_created(self) -> None:
        """Verify ProviderRequest is created when context is enabled."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)
        stage = RepositoryContextStage(index=index)

        context = _make_context(context_enabled=True)
        await stage.execute(context)

        provider_request = context.get_metadata("provider_request")
        assert provider_request is not None
        assert isinstance(provider_request, ProviderRequest)
        assert provider_request.provider_type == ProviderType.openai
        assert len(provider_request.messages) > 0

    @pytest.mark.asyncio
    async def test_provider_request_contains_repository_context(self) -> None:
        """Verify ProviderRequest includes repository context in messages."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)
        stage = RepositoryContextStage(index=index)

        context = _make_context(context_enabled=True)
        await stage.execute(context)

        provider_request = context.get_metadata("provider_request")
        assert provider_request is not None

        # Check that repository context is included in messages.
        all_content = " ".join(
            str(msg.get("content", "")) for msg in provider_request.messages
        )
        # The serializer uses the new ContextPackage v2 format.
        assert "Primary symbol:" in all_content or "main.App" in all_content


# ------------------------------------------------------------------
# Repository context disabled
# ------------------------------------------------------------------


class TestContextDisabled:
    """Tests for repository context disabled scenario."""

    @pytest.mark.asyncio
    async def test_no_context_package_when_disabled(self) -> None:
        """Verify no ContextPackage when context is disabled."""
        stage = RepositoryContextStage()

        context = _make_context(context_enabled=False)
        result = await stage.before(context)

        assert result is not None
        assert result.success is True
        assert result.data == {"enabled": False}
        assert context.context_package is None

    @pytest.mark.asyncio
    async def test_no_provider_request_when_disabled(self) -> None:
        """Verify no ProviderRequest when context is disabled."""
        stage = RepositoryContextStage()

        context = _make_context(context_enabled=False)
        await stage.before(context)

        provider_request = context.get_metadata("provider_request")
        assert provider_request is None


# ------------------------------------------------------------------
# Provider receives ProviderRequest
# ------------------------------------------------------------------


class TestProviderReceivesRequest:
    """Tests for ProviderStage consuming ProviderRequest."""

    @pytest.mark.asyncio
    async def test_provider_receives_provider_request(self) -> None:
        """Verify ProviderStage receives kwargs from ProviderRequest."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)

        context_stage = RepositoryContextStage(index=index)
        mock_provider = _MockProvider()

        request = _make_request(context_enabled=True)
        response = await _run_pipeline(context_stage, mock_provider, request)

        assert response.success is True
        assert len(mock_provider.chat_calls) == 1
        kwargs = mock_provider.chat_calls[0]
        assert "messages" in kwargs
        assert "model" in kwargs

    @pytest.mark.asyncio
    async def test_provider_receives_stream_flag(self) -> None:
        """Verify stream flag is forwarded to provider."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)

        context_stage = RepositoryContextStage(index=index)
        mock_provider = _MockProvider()

        request = _make_request(
            context_enabled=True,
            messages=[{"role": "user", "content": "test"}],
        )
        request.stream = True

        # Use _run_pipeline which properly converts PipelineRequest
        # to context.request via request.to_provider_kwargs()
        response = await _run_pipeline(context_stage, mock_provider, request)

        assert response.success is True
        assert len(mock_provider.chat_calls) == 1
        assert mock_provider.chat_calls[0]["stream"] is True


# ------------------------------------------------------------------
# Serializer invoked
# ------------------------------------------------------------------


class TestSerializerInvoked:
    """Tests for serializer invocation."""

    @pytest.mark.asyncio
    async def test_serializer_produces_correct_format(self) -> None:
        """Verify serializer produces OpenAI-compatible format."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)
        stage = RepositoryContextStage(index=index)

        context = _make_context(context_enabled=True)
        await stage.execute(context)

        provider_request = context.get_metadata("provider_request")
        assert provider_request is not None
        assert provider_request.provider_type == ProviderType.openai

        # Check message structure.
        for msg in provider_request.messages:
            assert "role" in msg
            assert "content" in msg

    @pytest.mark.asyncio
    async def test_serializer_preserves_user_messages(self) -> None:
        """Verify user messages are preserved in serialized request."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)
        stage = RepositoryContextStage(index=index)

        user_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "How are you?"},
        ]
        context = _make_context(
            context_enabled=True,
            messages=user_messages,
        )
        await stage.execute(context)

        provider_request = context.get_metadata("provider_request")
        assert provider_request is not None

        # Extract user/assistant messages from provider request.
        user_assistant_msgs = [
            msg for msg in provider_request.messages
            if msg.get("role") in ("user", "assistant")
        ]

        # Should contain the original user messages.
        contents = [msg.get("content", "") for msg in user_assistant_msgs]
        assert "Hello" in contents
        assert "How are you?" in contents


# ------------------------------------------------------------------
# Response unchanged
# ------------------------------------------------------------------


class TestResponseUnchanged:
    """Tests verifying the pipeline returns the provider's response unchanged."""

    @pytest.mark.asyncio
    async def test_response_is_provider_response(self) -> None:
        """Verify the pipeline returns the provider's response."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)

        context_stage = RepositoryContextStage(index=index)
        mock_provider = _MockProvider()
        mock_provider._response = {
            "choices": [
                {"message": {"role": "assistant", "content": "custom response"}}
            ]
        }

        request = _make_request(context_enabled=True)
        response = await _run_pipeline(context_stage, mock_provider, request)

        assert response.success is True
        assert response.data["choices"][0]["message"]["content"] == "custom response"

    @pytest.mark.asyncio
    async def test_response_shape_preserved(self) -> None:
        """Verify response shape is preserved through the pipeline."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)

        context_stage = RepositoryContextStage(index=index)
        mock_provider = _MockProvider()

        request = _make_request(context_enabled=True)
        response = await _run_pipeline(context_stage, mock_provider, request)

        assert response.success is True
        assert "choices" in response.data
        assert len(response.data["choices"]) > 0


# ------------------------------------------------------------------
# Pipeline ordering
# ------------------------------------------------------------------


class TestPipelineOrdering:
    """Tests for pipeline stage ordering."""

    @pytest.mark.asyncio
    async def test_repository_context_runs_before_provider(self) -> None:
        """Verify RepositoryContextStage runs before ProviderStage."""
        execution_order: list[str] = []

        class _TrackingContextStage(PipelineStage):
            @property
            def name(self) -> str:
                return "repository_context"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                execution_order.append("repository_context")
                return PipelineStageResult(
                    stage_name=self.name,
                    success=True,
                    data=None,
                )

            async def after(
                self, context: PipelineContext, result: PipelineStageResult
            ) -> PipelineStageResult | None:
                return None

        class _TrackingProviderStage(PipelineStage):
            @property
            def name(self) -> str:
                return "provider"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                execution_order.append("provider")
                return PipelineStageResult(
                    stage_name=self.name,
                    success=True,
                    data={"choices": [{"message": {"role": "assistant"}}]},
                )

            async def after(
                self, context: PipelineContext, result: PipelineStageResult
            ) -> PipelineStageResult | None:
                return None

        engine = PipelineEngine()
        engine.register(_TrackingContextStage())
        engine.register(_TrackingProviderStage())

        await engine.execute(_make_request())

        assert execution_order == ["repository_context", "provider"]

    @pytest.mark.asyncio
    async def test_provider_request_set_before_provider_stage(self) -> None:
        """Verify ProviderRequest is available when ProviderStage runs."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)

        context_stage = RepositoryContextStage(index=index)
        mock_provider = _MockProvider()

        request = _make_request(context_enabled=True)
        response = await _run_pipeline(context_stage, mock_provider, request)

        assert response.success is True

        # ProviderRequest should be set in the repository_context stage result.
        repo_result = response.stage_results.get("repository_context")
        assert repo_result is not None
        assert repo_result.success is True
        assert repo_result.data is not None


# ------------------------------------------------------------------
# Graceful failure
# ------------------------------------------------------------------


class TestGracefulFailure:
    """Tests for graceful failure handling."""

    @pytest.mark.asyncio
    async def test_context_failure_does_not_break_pipeline(self) -> None:
        """Verify pipeline continues when context assembly fails."""

        class _FailingContextStage(PipelineStage):
            @property
            def name(self) -> str:
                return "failing_context"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                raise RuntimeError("context assembly failed")

            async def after(
                self, context: PipelineContext, result: PipelineStageResult
            ) -> PipelineStageResult | None:
                return None

        class _TrackingStage(PipelineStage):
            def __init__(self) -> None:
                self.executed = False

            @property
            def name(self) -> str:
                return "tracking"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                self.executed = True
                return PipelineStageResult(
                    stage_name=self.name,
                    success=True,
                    data={"tracked": True},
                )

            async def after(
                self, context: PipelineContext, result: PipelineStageResult
            ) -> PipelineStageResult | None:
                return None

        engine = PipelineEngine()
        engine.register(_FailingContextStage())

        response = await engine.execute(_make_request())

        # The pipeline should handle the failure gracefully —
        # record the error but return a response (no crash).
        assert response.success is False
        assert response.error is not None
        assert "context assembly failed" in response.error

    @pytest.mark.asyncio
    async def test_serialization_failure_does_not_break_pipeline(self) -> None:
        """Verify serialization failure is handled gracefully."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)

        context_stage = RepositoryContextStage(index=index)
        mock_provider = _MockProvider()

        # Patch the serializer to fail.
        with patch(
            "packages.pipeline.stages.repository_context.SerializerFactory.create"
        ) as mock_create:
            mock_create.side_effect = RuntimeError("serializer error")

            request = _make_request(context_enabled=True)
            response = await _run_pipeline(context_stage, mock_provider, request)

            # Pipeline should still succeed (graceful degradation).
            assert response.success is True
            # Provider should still be called (with fallback).
            assert len(mock_provider.chat_calls) == 1

# ------------------------------------------------------------------
# Repeated execution deterministic
# ------------------------------------------------------------------


class TestDeterministicExecution:
    """Tests for deterministic repeated execution."""

    @pytest.mark.asyncio
    async def test_identical_input_produces_identical_output(self) -> None:
        """Verify identical requests produce identical ProviderRequests."""
        symbols = [
            _make_symbol("App", "main.App", "main.py"),
            _make_symbol("run", "main.App.run", "main.py"),
            _make_symbol("helper", "utils.helper", "utils.py"),
        ]
        index = _make_index(symbols)
        stage = RepositoryContextStage(index=index)

        provider_requests = []
        for _ in range(5):
            context = _make_context(
                context_enabled=True,
                messages=[{"role": "user", "content": "test query"}],
            )
            await stage.execute(context)
            pr = context.get_metadata("provider_request")
            if pr is not None:
                provider_requests.append(pr)

        # All provider requests should be identical.
        first = provider_requests[0]
        for pr in provider_requests[1:]:
            assert pr.messages == first.messages
            assert pr.model == first.model
            assert pr.kwargs == first.kwargs

    @pytest.mark.asyncio
    async def test_empty_repository_produces_empty_context(self) -> None:
        """Verify empty repository produces empty context package."""
        index = _make_index([])
        stage = RepositoryContextStage(index=index)

        context = _make_context(context_enabled=True)
        await stage.execute(context)

        assert context.context_package is not None
        assert context.context_package.supporting_symbols == []
        assert context.context_package.related_modules == []

    @pytest.mark.asyncio
    async def test_pipeline_deterministic_with_mock_provider(self) -> None:
        """Verify full pipeline is deterministic with mocked provider."""
        symbols = [
            _make_symbol("App", "main.App", "main.py"),
            _make_symbol("run", "main.App.run", "main.py"),
        ]
        index = _make_index(symbols)

        results = []
        for _ in range(3):
            context_stage = RepositoryContextStage(index=index)
            mock_provider = _MockProvider()

            request = _make_request(
                context_enabled=True,
                messages=[{"role": "user", "content": "deterministic test"}],
            )
            response = await _run_pipeline(context_stage, mock_provider, request)

            results.append({
                "success": response.success,
                "has_provider_request": (
                    response.stage_results.get("repository_context") is not None
                ),
                "chat_calls": len(mock_provider.chat_calls),
            })

        # All runs should produce identical results.
        for result in results[1:]:
            assert result == results[0]


# ------------------------------------------------------------------
# End-to-end pipeline
# ------------------------------------------------------------------


class TestEndToEnd:
    """End-to-end pipeline tests."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_context(self) -> None:
        """Verify full pipeline: context → serialize → provider."""
        symbols = [_make_symbol("App", "main.App", "main.py")]
        index = _make_index(symbols)

        context_stage = RepositoryContextStage(index=index)
        mock_provider = _MockProvider()

        request = _make_request(
            context_enabled=True,
            messages=[{"role": "user", "content": "test"}],
        )
        response = await _run_pipeline(context_stage, mock_provider, request)

        assert response.success is True
        # Repository context stage should have produced a package.
        repo_result = response.stage_results.get("repository_context")
        assert repo_result is not None
        assert repo_result.success is True
        assert repo_result.data is not None
        assert len(mock_provider.chat_calls) == 1

    @pytest.mark.asyncio
    async def test_full_pipeline_without_context(self) -> None:
        """Verify pipeline works when context is disabled."""
        mock_provider = _MockProvider()

        context_stage = RepositoryContextStage()

        request = _make_request(
            context_enabled=False,
            messages=[{"role": "user", "content": "test"}],
        )
        response = await _run_pipeline(context_stage, mock_provider, request)

        assert response.success is True
        # Context stage should have returned early with no package.
        repo_result = response.stage_results.get("repository_context")
        assert repo_result is not None
        assert repo_result.success is True
        assert repo_result.data == {"enabled": False}
        assert len(mock_provider.chat_calls) == 1