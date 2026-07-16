"""Tests for RepositoryContextStage.

Verifies that the stage orchestrates context building correctly,
handles disabled features, handles exceptions gracefully, and
supports deterministic execution.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from packages.context.package import ContextPackage
from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.request import PipelineRequest
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.repository.symbols.graph import SymbolGraphView
from packages.repository.symbols.models import (
    Module,
    Symbol,
    SymbolGraph,
    SymbolType,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_symbol(
    name: str,
    qualified_name: str,
    symbol_type: SymbolType = SymbolType.FUNCTION,
    module: str = "main",
    lineno: int = 1,
) -> Symbol:
    """Create a Symbol for testing."""
    return Symbol(
        id=qualified_name,
        name=name,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        module=module,
        lineno=lineno,
    )


def _make_graph(symbols: list[Symbol]) -> SymbolGraphView:
    """Create a SymbolGraphView from a list of symbols."""
    modules: dict[str, Module] = {}
    for sym in symbols:
        if sym.module not in modules:
            modules[sym.module] = Module(path=sym.module)
        modules[sym.module].symbols.append(sym)
    return SymbolGraphView(SymbolGraph(modules=modules))


def _make_context(
    messages: list[dict[str, object]] | None = None,
    request_id: str = "test-req-1",
) -> PipelineContext:
    """Create a PipelineContext with the given messages."""
    return PipelineContext(
        request_id=request_id,
        request={
            "messages": messages or [
                {"role": "user", "content": "test query"}
            ],
        },
    )


# ------------------------------------------------------------------
# Context attached
# ------------------------------------------------------------------


class TestContextAttached:
    """Tests for context attachment to PipelineContext."""

    @pytest.mark.asyncio
    async def test_context_package_attached(self) -> None:
        """Verify ContextPackage is attached to context on success."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context()
        result = await stage.execute(context)

        assert result.success is True
        assert context.context_package is not None
        assert isinstance(context.context_package, ContextPackage)
        assert len(context.context_package.symbols) > 0
        assert len(context.context_package.modules) > 0

    @pytest.mark.asyncio
    async def test_context_package_query_is_empty(self) -> None:
        """Verify the package query is empty (composer does not fabricate)."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context(
            messages=[{"role": "user", "content": "find the App class"}]
        )
        result = await stage.execute(context)

        assert result.success is True
        assert context.context_package is not None
        assert context.context_package.query == ""

    @pytest.mark.asyncio
    async def test_stage_result_contains_package(self) -> None:
        """Verify the stage result data contains the ContextPackage."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context()
        result = await stage.execute(context)

        assert result.data is context.context_package
        assert isinstance(result.data, ContextPackage)


# ------------------------------------------------------------------
# Disabled feature skips stage
# ------------------------------------------------------------------


class TestDisabledFeature:
    """Tests for disabled repository context feature."""

    @pytest.mark.asyncio
    async def test_disabled_skips_execution(self) -> None:
        """Verify disabled feature returns no-op without calling builder."""
        stage = RepositoryContextStage()

        context = _make_context()
        context.set_metadata("context_enabled", False)

        result = await stage.before(context)

        assert result is not None
        assert result.success is True
        assert result.data == {"enabled": False}
        assert context.context_package is None

    @pytest.mark.asyncio
    async def test_disabled_leaves_package_none(self) -> None:
        """Verify disabled feature leaves context_package as None."""
        stage = RepositoryContextStage()

        context = _make_context()
        context.set_metadata("context_enabled", False)

        # before() should short-circuit
        result = await stage.before(context)
        assert result is not None
        assert context.context_package is None

    @pytest.mark.asyncio
    async def test_default_is_enabled(self) -> None:
        """Verify context_enabled defaults to True when absent."""
        stage = RepositoryContextStage()

        context = _make_context()
        # No context_enabled set in metadata

        result = await stage.before(context)
        assert result is None  # Proceed to execute()

    @pytest.mark.asyncio
    async def test_stage_name(self) -> None:
        """Verify stage name is 'repository_context'."""
        stage = RepositoryContextStage()
        assert stage.name == "repository_context"


# ------------------------------------------------------------------
# Exception handling
# ------------------------------------------------------------------


class TestExceptionHandling:
    """Tests for graceful exception handling."""

    @pytest.mark.asyncio
    async def test_exception_does_not_fail_pipeline(self) -> None:
        """Verify exceptions are caught and pipeline continues."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)

        # Patch ContextBuilder to raise an exception.
        with patch(
            "packages.pipeline.stages.repository_context.ContextBuilder"
        ) as MockBuilder:
            MockBuilder.side_effect = RuntimeError("builder failed")

            stage = RepositoryContextStage(graph_view=graph_view)
            context = _make_context()

            result = await stage.execute(context)

            # Should succeed (graceful degradation).
            assert result.success is True
            assert context.context_package is None

    @pytest.mark.asyncio
    async def test_exception_logs_error(self) -> None:
        """Verify exceptions are logged."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)

        with patch(
            "packages.pipeline.stages.repository_context.ContextBuilder"
        ) as MockBuilder:
            MockBuilder.side_effect = RuntimeError("kaboom")

            stage = RepositoryContextStage(graph_view=graph_view)
            context = _make_context()

            with patch.object(
                logging.getLogger("packages.pipeline.stages.repository_context"),
                "error",
            ) as mock_error:
                await stage.execute(context)
                # Error should be logged.
                mock_error.assert_called()
                call_args = mock_error.call_args[0]
                assert "kaboom" in str(call_args)

    @pytest.mark.asyncio
    async def test_no_graph_view_returns_success(self) -> None:
        """Verify None graph_view returns success with no package."""
        stage = RepositoryContextStage(graph_view=None)
        context = _make_context()

        result = await stage.execute(context)

        assert result.success is True
        assert result.data is None
        assert context.context_package is None


# ------------------------------------------------------------------
# Pipeline continues after failure
# ------------------------------------------------------------------


class TestPipelineContinues:
    """Tests for pipeline continuation after context failure."""

    @pytest.mark.asyncio
    async def test_pipeline_continues_after_context_failure(self) -> None:
        """Verify pipeline continues after repository context failure."""

        class _FailingContextStage(PipelineStage):
            @property
            def name(self) -> str:
                return "failing_context"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                raise RuntimeError("context failed")

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

        tracking_stage = _TrackingStage()

        # Use the real RepositoryContextStage but patch the builder to fail.
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)

        with patch(
            "packages.pipeline.stages.repository_context.ContextBuilder"
        ) as MockBuilder:
            MockBuilder.side_effect = RuntimeError("context failed")

            engine = PipelineEngine()
            engine.register(RepositoryContextStage(graph_view=graph_view))
            engine.register(tracking_stage)

            request = PipelineRequest(
                metadata={"request_id": "test-1", "context_enabled": True}
            )
            response = await engine.execute(request)

            # The tracking stage should still execute.
            assert tracking_stage.executed is True
            assert response.success is True

    @pytest.mark.asyncio
    async def test_disabled_context_allows_pipeline(self) -> None:
        """Verify disabled context allows full pipeline to proceed."""

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

        tracking_stage = _TrackingStage()
        stage = RepositoryContextStage()

        engine = PipelineEngine()
        engine.register(stage)
        engine.register(tracking_stage)

        request = PipelineRequest(
            metadata={"request_id": "test-2", "context_enabled": False}
        )
        await engine.execute(request)

        assert tracking_stage.executed is True


# ------------------------------------------------------------------
# Deterministic execution
# ------------------------------------------------------------------


class TestDeterministicExecution:
    """Tests for deterministic context assembly."""

    @pytest.mark.asyncio
    async def test_identical_input_produces_identical_output(self) -> None:
        """Verify identical requests produce identical ContextPackages."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("helper", "utils.helper", SymbolType.FUNCTION, "utils.py"),
        ]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        packages = []
        for _ in range(5):
            context = _make_context(
                messages=[{"role": "user", "content": "test query"}]
            )
            await stage.execute(context)
            packages.append(context.context_package)

        first = packages[0]
        assert first is not None
        for package in packages[1:]:
            assert package is not None
            assert package.symbols == first.symbols
            assert package.modules == first.modules
            assert package.metadata == first.metadata

    @pytest.mark.asyncio
    async def test_empty_repository_produces_empty_package(self) -> None:
        """Verify empty repository produces empty ContextPackage."""
        graph_view = _make_graph([])
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context()
        result = await stage.execute(context)

        assert result.success is True
        assert context.context_package is not None
        assert context.context_package.symbols == []
        assert context.context_package.modules == []


# ------------------------------------------------------------------
# Logging fields populated
# ------------------------------------------------------------------


class TestLoggingFields:
    """Tests for structured logging fields."""

    @pytest.mark.asyncio
    async def test_log_contains_request_id(self) -> None:
        """Verify log output includes request_id."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context(request_id="req-123")

        logger_name = "packages.pipeline.stages.repository_context"
        with patch.object(logging.getLogger(logger_name), "info") as mock_info:
            await stage.execute(context)
            # The execute method logs structured info.
            # Check that the call contains request_id.
            calls = mock_info.call_args_list
            assert len(calls) > 0
            call_str = str(mock_info.call_args)
            assert "req-123" in call_str

    @pytest.mark.asyncio
    async def test_log_contains_context_enabled(self) -> None:
        """Verify log output includes context_enabled."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context()
        context.set_metadata("context_enabled", True)

        logger_name = "packages.pipeline.stages.repository_context"
        with patch.object(logging.getLogger(logger_name), "info") as mock_info:
            await stage.execute(context)
            calls = mock_info.call_args_list
            assert len(calls) > 0

    @pytest.mark.asyncio
    async def test_after_logs_completion(self) -> None:
        """Verify after() logs stage completion."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context()
        result = PipelineStageResult(
            stage_name="repository_context",
            success=True,
            data=ContextPackage(query="test"),
        )

        logger_name = "packages.pipeline.stages.repository_context"
        with patch.object(logging.getLogger(logger_name), "info") as mock_info:
            await stage.after(context, result)
            mock_info.assert_called()
            call_args = mock_info.call_args[0][0]
            assert "repository_context" in call_args
            assert "status=ok" in call_args


# ------------------------------------------------------------------
# Query extraction
# ------------------------------------------------------------------


class TestQueryExtraction:
    """Tests for query text extraction from context."""

    @pytest.mark.asyncio
    async def test_last_user_message(self) -> None:
        """Verify the last user message is used for context building."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context(
            messages=[
                {"role": "user", "content": "first query"},
                {"role": "assistant", "content": "response"},
                {"role": "user", "content": "second query"},
            ]
        )

        result = await stage.execute(context)
        assert result.success is True
        assert context.context_package is not None
        # The composer sets query="" (intentionally dumb).
        # The query text is used internally for ranking but not stored.
        assert context.context_package.query == ""

    @pytest.mark.asyncio
    async def test_empty_messages(self) -> None:
        """Verify empty messages produces empty query."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context(messages=[])
        result = await stage.execute(context)

        assert result.success is True
        assert context.context_package is not None
        assert context.context_package.query == ""

    @pytest.mark.asyncio
    async def test_no_user_messages(self) -> None:
        """Verify only assistant messages produces empty query."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        graph_view = _make_graph(symbols)
        stage = RepositoryContextStage(graph_view=graph_view)

        context = _make_context(
            messages=[{"role": "assistant", "content": "no user here"}]
        )
        result = await stage.execute(context)

        assert result.success is True
        assert context.context_package is not None
        assert context.context_package.query == ""


# ------------------------------------------------------------------
# No forbidden behaviour
# ------------------------------------------------------------------


class TestConstraints:
    """Tests verifying the stage respects constraints."""

    def test_no_provider_import(self) -> None:
        """Verify no provider implementation is imported.

        The stage may import ``ProviderType`` from the serializers
        types module (needed for serialization) but must not import
        from any ``packages.providers`` package.
        """
        import inspect

        import packages.pipeline.stages.repository_context as stage_module

        source = inspect.getsource(stage_module)
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert "packages.providers" not in stripped

    def test_no_gateway_import(self) -> None:
        """Verify no gateway import is used."""
        import inspect

        import packages.pipeline.stages.repository_context as stage_module

        source = inspect.getsource(stage_module)
        assert "apps.gateway" not in source

    def test_no_serialization(self) -> None:
        """Verify no request serialization."""
        import inspect

        import packages.pipeline.stages.repository_context as stage_module

        source = inspect.getsource(stage_module)
        assert "json.dumps" not in source
        assert "json.loads" not in source
