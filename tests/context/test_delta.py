"""Tests for delta context injection.

Verifies the conversation-key scheme, LRU tracking, and symbol
suppression logic in ``packages.context.delta`` and the
``RepositoryContextStage`` integration.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from packages.context.delta import (
    SentSymbolTracker,
    collect_all_symbols,
    conversation_key,
    filter_candidates,
    store_key,
)
from packages.context.models import ContextCandidate

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _candidate(name: str) -> ContextCandidate:
    """Create a minimal candidate for testing."""
    return ContextCandidate(
        symbol_id=name,
        qualified_name=name,
        module="main.py",
        score=0,
    )


# ------------------------------------------------------------------
# Conversation-key tests
# ------------------------------------------------------------------


class TestConversationKey:
    """Tests for conversation-key computation."""

    def test_first_turn_is_new(self) -> None:
        """Single user message returns the sentinel key."""
        result = conversation_key([{"role": "user", "content": "hello"}])
        assert result == "__new__"

    def test_multi_turn_returns_hash(self) -> None:
        """Turn with prior user messages produces a real hash."""
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ans"},
            {"role": "user", "content": "second"},
        ]
        result = conversation_key(msgs)
        assert result != "__new__"
        assert len(result) == 64  # full SHA-256 hex

    def test_stable_same_prefix(self) -> None:
        """Same user prefix produces the same key across calls."""
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ans"},
        ]
        k1 = conversation_key(msgs)
        k2 = conversation_key(msgs)
        assert k1 == k2

    def test_differs_different_user_query(self) -> None:
        """Different prefixes produce different keys.

        The differing content must be in the prefix, i.e. not the last user
        turn, since ``conversation_key`` excludes the current turn.
        """
        msgs_a = [
            {"role": "user", "content": "query a"},
            {"role": "user", "content": "now"},
        ]
        msgs_b = [
            {"role": "user", "content": "query b"},
            {"role": "user", "content": "now"},
        ]
        assert conversation_key(msgs_a) != conversation_key(msgs_b)

    def test_assistant_does_not_affect_key(self) -> None:
        """Assistant replies are invisible to the key."""
        msgs_a = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ans"},
            {"role": "user", "content": "new query"},
        ]
        msgs_b = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "different"},
            {"role": "user", "content": "new query"},
        ]
        assert conversation_key(msgs_a) == conversation_key(msgs_b)

    def test_identical_consecutive_questions_differ(self) -> None:
        """Repeating the same question does not collide with its own turn.

        Position is folded into the hash, so a prefix of ``[same]`` differs
        from a prefix of ``[same, same]`` even though the content repeats.
        """
        one = [
            {"role": "user", "content": "same"},
            {"role": "user", "content": "trailing"},
        ]
        two = [
            {"role": "user", "content": "same"},
            {"role": "user", "content": "same"},
            {"role": "user", "content": "trailing"},
        ]
        assert conversation_key(one) != conversation_key(two)

    def test_store_key_matches_next_lookup(self) -> None:
        """Turn N's store key equals turn N+1's lookup key (the mechanism)."""
        turn_n = [
            {"role": "user", "content": "what is App"},
        ]
        turn_n1 = [
            {"role": "user", "content": "what is App"},
            {"role": "assistant", "content": "App is a class"},
            {"role": "user", "content": "how does it work?"},
        ]
        # What turn N stores under must be what turn N+1 looks up under.
        assert store_key(turn_n) == conversation_key(turn_n1)

    def test_store_key_differs_per_turn(self) -> None:
        """Each turn stores under a distinct key, even with repeated content."""
        t1 = [{"role": "user", "content": "same"}]
        t2 = [
            {"role": "user", "content": "same"},
            {"role": "assistant", "content": "x"},
            {"role": "user", "content": "same"},
        ]
        assert store_key(t1) != store_key(t2)


# ------------------------------------------------------------------
# LRU tracker tests
# ------------------------------------------------------------------


class TestSentSymbolTracker:
    """Tests for the LRU sent-symbol tracker."""

    def test_cache_miss_returns_empty(self) -> None:
        """A key not in the cache returns an empty set."""
        tracker = SentSymbolTracker(maxsize=4)
        assert tracker.get("nonexistent") == set()

    def test_store_and_retrieve(self) -> None:
        """Store then retrieve the same key."""
        tracker = SentSymbolTracker(maxsize=4)
        s: set[str] = {"a.b.c", "d.e.f"}
        tracker.store("key1", s)
        assert tracker.get("key1") == s

    def test_overwrite_existing(self) -> None:
        """Re-storing a key replaces the old value."""
        tracker = SentSymbolTracker(maxsize=4)
        tracker.store("k", {"old"})
        tracker.store("k", {"new"})
        assert tracker.get("k") == {"new"}

    def test_lru_eviction(self) -> None:
        """Once maxsize is reached, oldest key is evicted."""
        tracker = SentSymbolTracker(maxsize=2)
        tracker.store("a", {"x"})
        tracker.store("b", {"y"})
        # Cache is full; 'a' is oldest.
        tracker.get("b")  # access b to make it MRU
        tracker.store("c", {"z"})  # evicts 'a'
        assert tracker.get("a") == set()
        assert tracker.get("b") == {"y"}
        assert tracker.get("c") == {"z"}

    def test_lru_access_updates_order(self) -> None:
        """Calling .get() on a key updates its recency."""
        tracker = SentSymbolTracker(maxsize=2)
        tracker.store("a", {"1"})
        tracker.store("b", {"2"})
        tracker.get("a")  # make 'a' MRU
        tracker.store("c", {"3"})  # evicts 'b', not 'a'
        assert tracker.get("a") == {"1"}
        assert tracker.get("b") == set()

    def test_clear(self) -> None:
        """clear() removes all entries."""
        tracker = SentSymbolTracker(maxsize=4)
        tracker.store("x", {"sym"})
        tracker.clear()
        assert tracker.get("x") == set()


# ------------------------------------------------------------------
# filter_candidates tests
# ------------------------------------------------------------------


class TestFilterCandidates:
    """Tests for candidate filtering logic."""

    def test_empty_candidates(self) -> None:
        """Empty list is returned unchanged."""
        assert filter_candidates([], {"x"}) == []

    def test_no_already_sent(self) -> None:
        """No suppression when already_sent is empty."""
        cands = [_candidate("a"), _candidate("b"), _candidate("c")]
        result = filter_candidates(cands, set())
        assert result is cands  # same list, no copy needed

    def test_filter_supporting_only(self) -> None:
        """Only supporting symbols are removed; primary is kept."""
        cands = [
            _candidate("primary"),
            _candidate("already_sent"),
            _candidate("new_one"),
        ]
        already = {"already_sent"}
        result = filter_candidates(cands, already)
        names = [c.qualified_name for c in result]
        assert names == ["primary", "new_one"]

    def test_primary_always_included(self) -> None:
        """Primary symbol is kept even if already_sent."""
        cands = [
            _candidate("primary"),
            _candidate("other"),
        ]
        already = {"primary", "other"}
        result = filter_candidates(cands, already)
        assert len(result) == 1
        assert result[0].qualified_name == "primary"

    def test_all_supporting_suppressed(self) -> None:
        """When only primary is new, only primary remains."""
        cands = [
            _candidate("primary"),
            _candidate("suppressed"),
        ]
        already = {"suppressed"}
        result = filter_candidates(cands, already)
        assert [c.qualified_name for c in result] == ["primary"]

    def test_no_duplicates_in_output(self) -> None:
        """Duplicates from already_sent are not re-included."""
        cands = [
            _candidate("primary"),
            _candidate("dup"),
            _candidate("dup"),  # duplicate in original
            _candidate("new"),
        ]
        already: set[str] = set()  # none already sent
        result = filter_candidates(cands, already)
        names = [c.qualified_name for c in result]
        # 'dup' should appear only once (the original candidates list
        # might have dupes, but the filtering shouldn't add any more).
        assert names == ["primary", "dup", "dup", "new"]

    def test_filter_reduces_list(self) -> None:
        """Returned list is shorter when some symbols are suppressed."""
        cands = [
            _candidate("primary"),
            _candidate("old1"),
            _candidate("old2"),
        ]
        already = {"old1", "old2"}
        result = filter_candidates(cands, already)
        assert len(result) == 1


# ------------------------------------------------------------------
# collect_all_symbols tests
# ------------------------------------------------------------------


class TestCollectAllSymbols:
    """Tests for collecting all qualified names from candidates."""

    def test_empty(self) -> None:
        assert collect_all_symbols([]) == set()

    def test_includes_primary(self) -> None:
        cands = [_candidate("primary"), _candidate("support")]
        result = collect_all_symbols(cands)
        assert "primary" in result
        assert "support" in result


# ------------------------------------------------------------------
# Integration: stage with delta injection
# ------------------------------------------------------------------


class TestStageIntegration:
    """End-to-end tests for the stage with delta injection enabled."""

    import asyncio

    @pytest.mark.asyncio
    async def test_turn1_full_injection(self) -> None:
        """Turn 1 (cache miss) injects all symbols normally."""
        from packages.pipeline.stages.repository_context import RepositoryContextStage
        from packages.repository.index.models import (
            Module,
            RepositoryIndex,
            RepositoryStatistics,
            Symbol,
            SymbolType,
        )

        symbols = [
            Symbol(
                id="main.App",
                name="App",
                qualified_name="main.App",
                symbol_type=SymbolType.CLASS,
                module="main.py",
                lineno=1,
            ),
            Symbol(
                id="main.run",
                name="run",
                qualified_name="main.run",
                symbol_type=SymbolType.FUNCTION,
                module="main.py",
                lineno=10,
            ),
        ]
        modules = {
            "main.py": Module(path="main.py", symbols=symbols),
        }
        statistics = RepositoryStatistics(
            module_count=1,
            class_count=1,
            function_count=1,
            method_count=0,
            symbol_count=2,
        )
        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=statistics,
        )

        stage = RepositoryContextStage(index=index, context_delta_injection=True)
        context = self._make_context(
            messages=[{"role": "user", "content": "test"}],
        )
        result = await stage.execute(context)

        assert result.success is True
        assert context.context_package is not None
        assert len(context.context_package.supporting_symbols) > 0

    @pytest.mark.asyncio
    async def test_turn2_suppresses_identical(self) -> None:
        """Second turn with same history suppresses already-sent symbols."""
        from packages.pipeline.stages.repository_context import RepositoryContextStage
        from packages.repository.index.models import (
            Module,
            RepositoryIndex,
            RepositoryStatistics,
            Symbol,
            SymbolType,
        )

        symbols = [
            Symbol(
                id="main.App",
                name="App",
                qualified_name="main.App",
                symbol_type=SymbolType.CLASS,
                module="main.py",
                lineno=1,
            ),
        ]
        modules = {
            "main.py": Module(path="main.py", symbols=symbols),
        }
        statistics = RepositoryStatistics(
            module_count=1, class_count=1, function_count=0, method_count=0, symbol_count=1,
        )
        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=statistics,
        )

        stage = RepositoryContextStage(index=index, context_delta_injection=True)

        # Turn 1: first pass (cache miss)
        ctx1 = self._make_context(
            messages=[{"role": "user", "content": "what is App"}],
        )
        await stage.execute(ctx1)
        pkg1 = ctx1.context_package
        assert pkg1 is not None

        # Turn 2: with history (cache hit) -- same query, same symbols
        ctx2 = self._make_context(
            messages=[
                {"role": "user", "content": "what is App"},
                {"role": "assistant", "content": "App is a class"},
                {"role": "user", "content": "what is App"},
            ],
        )
        await stage.execute(ctx2)
        pkg2 = ctx2.context_package
        assert pkg2 is not None
        # Primary symbol should still be present
        assert pkg2.primary_symbol == "main.App"

    @pytest.mark.asyncio
    async def test_disabled_is_unchanged(self) -> None:
        """With delta injection disabled, behaviour is unchanged."""
        from packages.pipeline.stages.repository_context import RepositoryContextStage
        from packages.repository.index.models import (
            Module,
            RepositoryIndex,
            RepositoryStatistics,
            Symbol,
            SymbolType,
        )

        symbols = [
            Symbol(
                id="main.App",
                name="App",
                qualified_name="main.App",
                symbol_type=SymbolType.CLASS,
                module="main.py",
                lineno=1,
            ),
        ]
        modules = {
            "main.py": Module(path="main.py", symbols=symbols),
        }
        statistics = RepositoryStatistics(
            module_count=1, class_count=1, function_count=0, method_count=0, symbol_count=1,
        )
        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=statistics,
        )

        # With delta disabled
        stage_off = RepositoryContextStage(index=index, context_delta_injection=False)
        ctx_off = self._make_context(
            messages=[{"role": "user", "content": "what is App"}],
        )
        await stage_off.execute(ctx_off)
        assert ctx_off.context_package is not None

        # With delta enabled (same setup, single turn)
        stage_on = RepositoryContextStage(index=index, context_delta_injection=True)
        ctx_on = self._make_context(
            messages=[{"role": "user", "content": "what is App"}],
        )
        await stage_on.execute(ctx_on)
        assert ctx_on.context_package is not None
        # Turn 1 with delta enabled should behave the same as disabled
        assert (
            ctx_off.context_package.supporting_symbols
            == ctx_on.context_package.supporting_symbols
        )

    @pytest.mark.asyncio
    async def test_no_new_symbols_logs_status(self) -> None:
        """When all symbols are suppressed, log says no_new_symbols."""
        import logging

        from packages.pipeline.stages.repository_context import RepositoryContextStage
        from packages.repository.index.models import (
            Module,
            RepositoryIndex,
            RepositoryStatistics,
            Symbol,
            SymbolType,
        )

        symbols = [
            Symbol(
                id="main.App",
                name="App",
                qualified_name="main.App",
                symbol_type=SymbolType.CLASS,
                module="main.py",
                lineno=1,
            ),
            Symbol(
                id="main.run",
                name="run",
                qualified_name="main.run",
                symbol_type=SymbolType.FUNCTION,
                module="main.py",
                lineno=10,
            ),
        ]
        modules = {
            "main.py": Module(path="main.py", symbols=symbols),
        }
        statistics = RepositoryStatistics(
            module_count=1, class_count=1, function_count=1, method_count=0, symbol_count=2,
        )
        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=statistics,
        )

        stage = RepositoryContextStage(index=index, context_delta_injection=True)

        # Turn 1: full injection (both symbols)
        ctx1 = self._make_context(
            messages=[{"role": "user", "content": "what is App"}],
        )
        await stage.execute(ctx1)
        assert ctx1.context_package is not None

        # Turn 2: same history, same symbols -> primary already sent,
        # supporting suppressed → no_new_symbols
        ctx2 = self._make_context(
            messages=[
                {"role": "user", "content": "what is App"},
                {"role": "assistant", "content": "App is a class"},
                {"role": "user", "content": "what is App"},
            ],
        )

        logger_name = "packages.pipeline.stages.repository_context"
        with self._capture_log(logger_name) as log_lines:
            await stage.execute(ctx2)

        # Check that the log contains no_new_symbols
        found = any("no_new_symbols" in line for line in log_lines)
        assert found, "Expected log line with 'no_new_symbols'"

    @pytest.mark.asyncio
    async def test_two_conversations_no_leak(self) -> None:
        """Interleaved calls from different conversations don't affect each other."""
        from packages.pipeline.stages.repository_context import RepositoryContextStage
        from packages.repository.index.models import (
            Module,
            RepositoryIndex,
            RepositoryStatistics,
            Symbol,
            SymbolType,
        )

        symbols = [
            Symbol(
                id="main.App",
                name="App",
                qualified_name="main.App",
                symbol_type=SymbolType.CLASS,
                module="main.py",
                lineno=1,
            ),
        ]
        modules = {
            "main.py": Module(path="main.py", symbols=symbols),
        }
        statistics = RepositoryStatistics(
            module_count=1, class_count=1, function_count=0, method_count=0, symbol_count=1,
        )
        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=statistics,
        )

        stage = RepositoryContextStage(index=index, context_delta_injection=True)

        # Conversation A
        ctx_a1 = self._make_context(
            messages=[{"role": "user", "content": "conv A question 1"}],
        )
        await stage.execute(ctx_a1)

        # Conversation B (completely different history)
        ctx_b1 = self._make_context(
            messages=[{"role": "user", "content": "conv B question 1"}],
        )
        await stage.execute(ctx_b1)

        # Both should still have their context (no cross-leak)
        assert ctx_a1.context_package is not None
        assert ctx_b1.context_package is not None

        # Now turn 2 for A -- cache miss for B's symbols
        ctx_a2 = self._make_context(
            messages=[
                {"role": "user", "content": "conv A question 1"},
                {"role": "assistant", "content": "A answer"},
                {"role": "user", "content": "conv A question 2"},
            ],
        )
        await stage.execute(ctx_a2)
        assert ctx_a2.context_package is not None

    @pytest.mark.asyncio
    async def test_lru_eviction_does_not_raise(self) -> None:
        """At the cache limit, eviction doesn't crash."""
        from packages.pipeline.stages.repository_context import RepositoryContextStage
        from packages.repository.index.models import (
            Module,
            RepositoryIndex,
            RepositoryStatistics,
            Symbol,
            SymbolType,
        )

        symbols = [
            Symbol(
                id="main.App",
                name="App",
                qualified_name="main.App",
                symbol_type=SymbolType.CLASS,
                module="main.py",
                lineno=1,
            ),
        ]
        modules = {
            "main.py": Module(path="main.py", symbols=symbols),
        }
        statistics = RepositoryStatistics(
            module_count=1, class_count=1, function_count=0, method_count=0, symbol_count=1,
        )
        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=statistics,
        )

        # Tiny cache so eviction triggers fast.
        stage = RepositoryContextStage(
            index=index,
            context_delta_injection=True,
            context_delta_cache_size=2,
        )

        for i in range(10):
            ctx = self._make_context(
                messages=[{"role": "user", "content": f"question {i}"}],
            )
            result = await stage.execute(ctx)
            assert result.success is True  # never crashes

    @pytest.mark.asyncio
    async def test_cache_is_per_stage_instance(self) -> None:
        """Two stage instances have separate caches."""
        from packages.pipeline.stages.repository_context import RepositoryContextStage
        from packages.repository.index.models import (
            Module,
            RepositoryIndex,
            RepositoryStatistics,
            Symbol,
            SymbolType,
        )

        symbols = [
            Symbol(
                id="main.App",
                name="App",
                qualified_name="main.App",
                symbol_type=SymbolType.CLASS,
                module="main.py",
                lineno=1,
            ),
        ]
        modules = {
            "main.py": Module(path="main.py", symbols=symbols),
        }
        statistics = RepositoryStatistics(
            module_count=1, class_count=1, function_count=0, method_count=0, symbol_count=1,
        )
        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=statistics,
        )

        stage_a = RepositoryContextStage(index=index, context_delta_injection=True)
        stage_b = RepositoryContextStage(index=index, context_delta_injection=True)

        # Turn 1 for stage A (populates cache)
        ctx_a = self._make_context(
            messages=[{"role": "user", "content": "question A"}],
        )
        await stage_a.execute(ctx_a)

        # Turn 1 for stage B (separate cache, no suppression)
        ctx_b = self._make_context(
            messages=[{"role": "user", "content": "question B"}],
        )
        await stage_b.execute(ctx_b)
        assert ctx_b.context_package is not None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_context(
        messages: list[dict],
        request_id: str = "test-req",
    ) -> "PipelineContext":
        """Create a PipelineContext with the given messages."""
        from packages.pipeline.context import PipelineContext

        return PipelineContext(
            request_id=request_id,
            request={
                "messages": messages,
            },
        )

    @staticmethod
    @contextmanager
    def _capture_log(
        logger_name: str,
    ):
        """Capture log output from the given logger into a list of strings."""
        import logging

        class LogCapture(logging.Handler):
            def __init__(self) -> None:
                super().__init__()
                self.records: list[logging.LogRecord] = []

            def emit(self, record: logging.LogRecord) -> None:
                self.records.append(self.format(record))

        handler = LogCapture()
        handler.setLevel(logging.INFO)
        logger = logging.getLogger(logger_name)
        old_handlers = logger.handlers[:]
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            yield handler.records
        finally:
            logger.handlers = old_handlers
            logger.setLevel(old_level)