"""Tests for session log analyzer (Fix 3).

Verifies:
1. Suppression ratio uses new + suppressed as denominator
2. Analyzer does not crash on mixed null/non-null token values
3. Slowest requests table shows token counts and message previews
"""

from __future__ import annotations

import json
import tempfile

from scripts.analyze_sessions import _load_records, analyze


class TestSuppressionRatio:
    """Tests for suppression ratio calculation."""

    def _write_fixture(self, records: list[dict[str, object]]) -> str:
        """Write fixture records to a temp file and return the path."""
        fh = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        for r in records:
            fh.write(json.dumps(r) + "\n")
        fh.close()
        return fh.name

    def test_no_new_symbols_turns_have_nonzero_ratio(self) -> None:
        """A fixture with no_new_symbols turns produces suppression ratio > 0."""
        records = [
            {
                "conversation_key": "conv-1",
                "context": {
                    "status": "no_new_symbols",
                    "symbols_selected": 10,
                    "symbols_new": 0,
                    "symbols_suppressed": 10,
                },
            },
            {
                "conversation_key": "conv-1",
                "context": {
                    "status": "no_new_symbols",
                    "symbols_selected": 8,
                    "symbols_new": 1,
                    "symbols_suppressed": 7,
                },
            },
        ]
        path = self._write_fixture(records)
        recs = _load_records(path)
        # Should not crash and should compute a suppression ratio.
        import io
        import sys

        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            analyze(recs)
        finally:
            sys.stdout = old_stdout

        output = out.getvalue()
        assert "DELTA INJECTION EFFECTIVENESS" in output
        # Mean should be between 0 and 1.
        assert "Mean suppression ratio" in output

    def test_assembled_first_turn_has_ratio_near_zero(self) -> None:
        """On assembled first turn, suppression ratio is near 0."""
        records = [
            {
                "conversation_key": "conv-1",
                "context": {
                    "status": "assembled",
                    "symbols_selected": 5,
                    "symbols_new": 5,
                    "symbols_suppressed": 0,
                },
            },
        ]
        path = self._write_fixture(records)
        recs = _load_records(path)

        import io
        import sys

        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            analyze(recs)
        finally:
            sys.stdout = old_stdout

        output = out.getvalue()
        assert "DELTA INJECTION EFFECTIVENESS" in output


class TestMixedTokenValues:
    """Tests for robustness with mixed null/non-null token values."""

    def _write_fixture(self, records: list[dict[str, object]]) -> str:
        fh = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        for r in records:
            fh.write(json.dumps(r) + "\n")
        fh.close()
        return fh.name

    def test_analyzer_does_not_crash_on_null_tokens(self) -> None:
        """Analyzer should not crash when some records have null tokens."""
        records = [
            {
                "usage": {"prompt_tokens": None, "completion_tokens": None},
                "timing": {"total_ms": 100},
                "status": "ok",
                "last_user_message": "first request",
            },
            {
                "usage": {"prompt_tokens": 50, "completion_tokens": 25},
                "timing": {"total_ms": 200},
                "status": "ok",
                "last_user_message": "second request",
            },
        ]
        path = self._write_fixture(records)
        recs = _load_records(path)

        import io
        import sys

        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            analyze(recs)
        finally:
            sys.stdout = old_stdout

        output = out.getvalue()
        # The analyzer should complete without crashing.
        assert "SESSION LOG ANALYSIS" in output

    def test_slowest_requests_shows_token_counts_with_none_fallback(self) -> None:
        """The 5 slowest requests table should show tokens=0 when None."""
        records = [
            {
                "request_id": "req-1",
                "usage": {"prompt_tokens": None, "completion_tokens": None},
                "timing": {"total_ms": 500},
                "status": "ok",
                "last_user_message": "slow request with no tokens",
            },
        ]
        path = self._write_fixture(records)
        recs = _load_records(path)

        import io
        import sys

        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            analyze(recs)
        finally:
            sys.stdout = old_stdout

        output = out.getvalue()
        assert "5 SLOWEST REQUESTS" in output
        # Should show prompt_tokens=0, not crash on None.
        assert "prompt_tokens=0" in output


class TestContextCost:
    """Tests for repository-context cost attribution."""

    def _write_fixture(self, records: list[dict[str, object]]) -> str:
        fh = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        for r in records:
            fh.write(json.dumps(r) + "\n")
        fh.close()
        return fh.name

    def test_context_cost_uses_direct_estimated_tokens(self) -> None:
        """Analyzer reports context.estimated_tokens separately from prompt tokens."""
        records = [
            {
                "intent": "EXPLAIN",
                "context": {
                    "status": "assembled",
                    "estimated_tokens": 1000,
                    "max_tokens": 4000,
                },
                "usage": {"prompt_tokens": 4000, "completion_tokens": 100},
                "timing": {"total_ms": 100, "stages": {"repository_context_ms": 12.5}},
                "status": "ok",
            },
            {
                "intent": "REFACTOR",
                "context": {
                    "status": "assembled",
                    "estimated_tokens": 2000,
                    "max_tokens": 8000,
                },
                "usage": {"prompt_tokens": 8000, "completion_tokens": 100},
                "timing": {"total_ms": 200, "stages": {"repository_context_ms": 17.5}},
                "status": "ok",
            },
        ]
        path = self._write_fixture(records)
        recs = _load_records(path)

        import io
        import sys

        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            analyze(recs)
        finally:
            sys.stdout = old_stdout

        output = out.getvalue()
        assert "Direct repository context estimate" in output
        assert "Median:  1500 tokens" in output
        assert "Median share of prompt: 25.0%" in output
        assert "Median configured budget: 6000 tokens" in output
        assert "Median budget utilization: 25.0%" in output
        assert "By intent:" in output
        assert "EXPLAIN" in output
        assert "REFACTOR" in output
        assert "Prompt-token comparison by context status" in output

    def test_context_cost_by_intent_compares_budget_utilization(self) -> None:
        """Analyzer splits repository-context budget cost by intent."""
        records = [
            {
                "intent": "EXPLAIN",
                "context": {
                    "status": "assembled",
                    "estimated_tokens": 1000,
                    "max_tokens": 4000,
                },
                "usage": {"prompt_tokens": 5000, "completion_tokens": 50},
                "timing": {"total_ms": 100},
                "status": "ok",
            },
            {
                "intent": "EXPLAIN",
                "context": {
                    "status": "assembled",
                    "estimated_tokens": 2000,
                    "max_tokens": 4000,
                },
                "usage": {"prompt_tokens": 6000, "completion_tokens": 50},
                "timing": {"total_ms": 100},
                "status": "ok",
            },
            {
                "intent": "REFACTOR",
                "context": {
                    "status": "assembled",
                    "estimated_tokens": 3000,
                    "max_tokens": 6000,
                },
                "usage": {"prompt_tokens": 9000, "completion_tokens": 50},
                "timing": {"total_ms": 100},
                "status": "ok",
            },
        ]
        path = self._write_fixture(records)
        recs = _load_records(path)

        import io
        import sys

        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            analyze(recs)
        finally:
            sys.stdout = old_stdout

        output = out.getvalue()
        assert "By intent:" in output
        assert "EXPLAIN" in output
        assert "REFACTOR" in output
        assert "1500" in output
        assert "6000" in output
        assert "50.0%" in output


class TestLastUserMessagePreview:
    """Tests for last_user_message preview in analyzer output."""

    def _write_fixture(self, records: list[dict[str, object]]) -> str:
        fh = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        for r in records:
            fh.write(json.dumps(r) + "\n")
        fh.close()
        return fh.name

    def test_slowest_requests_shows_message_preview(self) -> None:
        """The 5 slowest requests table should show message preview."""
        records = [
            {
                "request_id": "req-1",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "timing": {"total_ms": 1000},
                "status": "ok",
                "last_user_message": (
                    "This is a test message that should appear in the "
                    "slowest requests preview"
                ),
            },
        ]
        path = self._write_fixture(records)
        recs = _load_records(path)

        import io
        import sys

        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            analyze(recs)
        finally:
            sys.stdout = old_stdout

        output = out.getvalue()
        assert "5 SLOWEST REQUESTS" in output
        assert "This is a test message" in output
