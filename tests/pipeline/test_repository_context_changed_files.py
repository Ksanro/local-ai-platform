"""Focused tests for the change-aware wiring in RepositoryContextStage.

The stage must stay inert by default, must forward the changed module keys it
is given to the builder, and must degrade to today's behaviour when the source
fails.  No test here touches Git: the stage only consumes an injected source.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from packages.context.models import ContextBudgetResult, ContextResult
from packages.pipeline.context import PipelineContext
from packages.pipeline.stages import repository_context as stage_module
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.repository.changed_files import ChangedFilesSignal
from packages.repository.git_changes import GitChangeSnapshot, GitChangeStatus, GitFileChange
from packages.repository.index.models import (
    Module,
    RepositoryIndex,
    RepositoryStatistics,
    Symbol,
)
from packages.repository.symbols.models import SymbolType

CHANGED_KEY = "packages/context/builder"
REPO_ROOT = Path("/repo")


class _RecordingBuilder:
    """Stand-in for ``ContextBuilder`` that captures constructor arguments."""

    instances: list[_RecordingBuilder] = []

    def __init__(
        self,
        index: Any,
        chars_per_token: float = 4.0,
        changed_modules: frozenset[str] = frozenset(),
    ) -> None:
        self.index = index
        self.chars_per_token = chars_per_token
        self.changed_modules = changed_modules
        _RecordingBuilder.instances.append(self)

    def build(self, query: Any, primary_symbol: Any = None) -> ContextResult:
        """Return an empty result so assembly stops early and deterministically."""
        return ContextResult(
            candidates=[],
            selected_modules=[],
            budget=ContextBudgetResult(),
        )


class _StubSource:
    """Changed-module source with a fixed answer and a call counter."""

    def __init__(self, paths: frozenset[str], error: Exception | None = None) -> None:
        self.paths = paths
        self.calls = 0
        self._error = error

    def module_paths(self) -> frozenset[str]:
        """Return the scripted paths, or raise the scripted error."""
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self.paths


class _Clock:
    """Manually advanced monotonic clock."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _index() -> RepositoryIndex:
    """A one-symbol repository index."""
    symbol = Symbol(
        id="packages.context.builder.ContextBuilder",
        name="ContextBuilder",
        qualified_name="packages.context.builder.ContextBuilder",
        symbol_type=SymbolType.CLASS,
        module=CHANGED_KEY,
        lineno=1,
    )
    return RepositoryIndex(
        modules={CHANGED_KEY: Module(path=CHANGED_KEY, symbols=[symbol])},
        _symbols=[symbol],
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=1,
            class_count=1,
            function_count=0,
            method_count=0,
            symbol_count=1,
        ),
    )


def _context(text: str = "how does the builder rank symbols") -> PipelineContext:
    """A minimal pipeline context carrying one user message."""
    return PipelineContext(
        request_id="test-changed-files",
        request={"messages": [{"role": "user", "content": text}]},
    )


@pytest.fixture(autouse=True)
def _fake_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the module-level ``ContextBuilder`` for the duration of a test."""
    _RecordingBuilder.instances.clear()
    monkeypatch.setattr(stage_module, "ContextBuilder", _RecordingBuilder)


@pytest.mark.asyncio
async def test_disabled_by_default_forwards_no_modules() -> None:
    """Without a source the builder sees an empty changed set."""
    stage = RepositoryContextStage(index=_index())

    result = await stage.execute(_context())

    assert result.success is True
    assert _RecordingBuilder.instances[0].changed_modules == frozenset()
    assert result.data is not None
    assert result.data["changed_files_count"] == 0


@pytest.mark.asyncio
async def test_enabled_source_forwards_modules_to_builder() -> None:
    """The snapshot's module keys reach the ranking layer."""
    stage = RepositoryContextStage(
        index=_index(),
        changed_files=_StubSource(frozenset({CHANGED_KEY})),
    )

    result = await stage.execute(_context())

    assert _RecordingBuilder.instances[0].changed_modules == frozenset({CHANGED_KEY})
    assert result.data is not None
    assert result.data["changed_files_count"] == 1


@pytest.mark.asyncio
async def test_source_is_read_once_per_request() -> None:
    """Reading is one cache lookup per request, never a Git run per symbol."""
    source = _StubSource(frozenset({CHANGED_KEY}))
    stage = RepositoryContextStage(index=_index(), changed_files=source)

    await stage.execute(_context())
    await stage.execute(_context())

    assert source.calls == 2
    assert all(b.changed_modules == frozenset({CHANGED_KEY}) for b in _RecordingBuilder.instances)


@pytest.mark.asyncio
async def test_failing_source_degrades_to_current_behaviour() -> None:
    """A broken source must never break or change the request path."""
    stage = RepositoryContextStage(
        index=_index(),
        changed_files=_StubSource(frozenset({CHANGED_KEY}), error=RuntimeError("boom")),
    )

    result = await stage.execute(_context())

    assert result.success is True
    assert _RecordingBuilder.instances[0].changed_modules == frozenset()


@pytest.mark.asyncio
async def test_signal_end_to_end_captures_once() -> None:
    """A real signal object works with the stage and captures exactly once."""
    snapshot = GitChangeSnapshot(
        repository_root=REPO_ROOT,
        branch="main",
        unstaged=(
            GitFileChange(
                index_status=".",
                worktree_status="M",
                status=GitChangeStatus.MODIFIED,
                path="packages/context/builder.py",
            ),
        ),
    )
    signal = ChangedFilesSignal(REPO_ROOT, capturer=lambda path: snapshot)
    stage = RepositoryContextStage(index=_index(), changed_files=signal)

    await stage.execute(_context())
    await stage.execute(_context())

    assert _RecordingBuilder.instances[0].changed_modules == frozenset({CHANGED_KEY})
    assert signal.capture_count == 1


@pytest.mark.asyncio
async def test_positive_ttl_keeps_git_out_of_the_request_path() -> None:
    """Even with refreshing enabled, a request only ever reads the cache.

    The TTL window is honoured by the background refresher, never by the
    stage, so a slow ``git status`` cannot delay whoever is waiting for a
    completion.
    """
    clock = _Clock()
    captures: list[Path] = []

    def capturer(path: Path) -> GitChangeSnapshot:
        captures.append(path)
        return GitChangeSnapshot(
            repository_root=REPO_ROOT,
            branch="main",
            unstaged=(
                GitFileChange(
                    index_status=".",
                    worktree_status="M",
                    status=GitChangeStatus.MODIFIED,
                    path="packages/context/builder.py",
                ),
            ),
        )

    signal = ChangedFilesSignal(REPO_ROOT, ttl_seconds=30.0, capturer=capturer, clock=clock)
    signal.prime()
    stage = RepositoryContextStage(index=_index(), changed_files=signal)

    for _ in range(5):
        clock.advance(60.0)  # every window has long since expired
        result = await stage.execute(_context())
        assert result.success is True

    assert captures == [REPO_ROOT]
    assert signal.capture_count == 1
    assert all(b.changed_modules == frozenset({CHANGED_KEY}) for b in _RecordingBuilder.instances)
    assert signal.refresh() is True  # the refresher's call is what recaptures
    assert len(captures) == 2
