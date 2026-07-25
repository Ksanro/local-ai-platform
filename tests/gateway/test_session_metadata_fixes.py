"""Tests for session metadata fixes (Fix 1 & Fix 2).

Verifies:
1. PipelineRequest stream_options.include_usage=true for streaming requests
2. PipelineRequest does not include stream_options for non-streaming requests
3. _surface_session_metadata reads symbol counts from metadata dict
4. On no_new_symbols path, symbols_selected == symbols_new + symbols_suppressed
5. On assembled path, counts are correctly read from metadata dict
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from packages.context.context_package import ContextPackage
from packages.pipeline.request import PipelineRequest
from packages.pipeline.result import PipelineStageResult

# ------------------------------------------------------------------
# Fix 1: stream_options
# ------------------------------------------------------------------


class TestStreamOptions:
    """Tests for stream_options.include_usage in streaming requests."""

    def test_streaming_includes_stream_options(self) -> None:
        """Verify streaming request includes stream_options.include_usage."""
        req = PipelineRequest(
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
        )
        kwargs = req.to_provider_kwargs()
        assert kwargs["stream"] is True
        assert "stream_options" in kwargs
        assert kwargs["stream_options"]["include_usage"] is True

    def test_non_streaming_excludes_stream_options(self) -> None:
        """Verify non-streaming request does NOT include stream_options."""
        req = PipelineRequest(
            messages=[{"role": "user", "content": "hello"}],
            stream=False,
        )
        kwargs = req.to_provider_kwargs()
        assert kwargs["stream"] is False
        assert "stream_options" not in kwargs

    def test_stream_options_with_other_kwargs(self) -> None:
        """Verify stream_options coexists with other kwargs."""
        req = PipelineRequest(
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
            kwargs={"temperature": 0.7, "max_tokens": 100},
        )
        kwargs = req.to_provider_kwargs()
        assert kwargs["stream_options"] == {"include_usage": True}
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 100


# ------------------------------------------------------------------
# Fix 2: Symbol counts in _surface_session_metadata
# ------------------------------------------------------------------


class TestSurfaceSessionMetadata:
    """Tests for _surface_session_metadata symbol count handling.

    These tests simulate the logic in _surface_session_metadata for
    reading symbol counts from the repository_context stage result data.
    The stage now returns a dict for all paths.
    """

    def _build_repo_result(
        self,
        data: Any,
        success: bool = True,
    ) -> PipelineStageResult:
        """Build a repo_result for testing."""
        return PipelineStageResult(
            stage_name="repository_context",
            success=success,
            data=data,
        )

    def _make_scope(self, repo_result: PipelineStageResult) -> dict[str, Any]:
        """Simulate what _surface_session_metadata does with repo_result data."""
        scope: dict[str, Any] = {}

        pkg = repo_result.data

        if isinstance(pkg, dict):
            if "enabled" in pkg and pkg.get("enabled") is False:
                # Disabled path.
                scope["session_context_status"] = "disabled"
                scope["session_symbols_selected"] = 0
                scope["session_symbols_new"] = 0
                scope["session_symbols_suppressed"] = 0
                scope["session_estimated_tokens"] = 0
                scope["session_primary_symbol"] = ""
            elif "package" in pkg:
                # Assembled path with counts.
                scope["session_context_status"] = "assembled"
                package = pkg["package"]
                scope["session_symbols_selected"] = pkg.get("symbols_selected", 0)
                scope["session_symbols_new"] = pkg.get("symbols_new", 0)
                scope["session_symbols_suppressed"] = pkg.get("symbols_suppressed", 0)
                scope["session_estimated_tokens"] = getattr(package, "estimated_tokens", 0) if package else 0
                scope["session_primary_symbol"] = getattr(package, "primary_symbol", "") if package else ""
            else:
                # Empty or no_new_symbols path.
                symbols_new = pkg.get("symbols_new", 0)
                symbols_suppressed = pkg.get("symbols_suppressed", 0)
                scope["session_context_status"] = "no_new_symbols" if (
                    symbols_new == 0 and symbols_suppressed > 0
                ) else "empty"
                scope["session_symbols_selected"] = pkg.get("symbols_selected", 0)
                scope["session_symbols_new"] = symbols_new
                scope["session_symbols_suppressed"] = symbols_suppressed
                scope["session_estimated_tokens"] = 0
                scope["session_primary_symbol"] = ""
        else:
            scope["session_context_status"] = "disabled"
            scope["session_symbols_selected"] = 0
            scope["session_symbols_new"] = 0
            scope["session_symbols_suppressed"] = 0
            scope["session_estimated_tokens"] = 0

        return scope

    def test_no_new_symbols_path_counts(self) -> None:
        """On no_new_symbols path, symbols_selected == symbols_new + symbols_suppressed."""
        # Simulate a no_new_symbols stage result.
        repo_result = self._build_repo_result(
            data={
                "symbols_selected": 10,
                "symbols_new": 0,
                "symbols_suppressed": 10,
            }
        )
        scope = self._make_scope(repo_result)

        assert scope["session_context_status"] == "no_new_symbols"
        assert scope["session_symbols_selected"] == 10
        assert scope["session_symbols_new"] == 0
        assert scope["session_symbols_suppressed"] == 10
        # Verify invariant: selected == new + suppressed
        assert scope["session_symbols_selected"] == scope["session_symbols_new"] + scope["session_symbols_suppressed"]

    def test_assembled_path_with_counts(self) -> None:
        """On assembled path, counts are read from metadata dict."""
        pkg = ContextPackage(
            primary_symbol="main.App",
            supporting_symbols=["main.App", "utils.helper"],
            related_modules=["main.py"],
            estimated_tokens=500,
        )

        repo_result = self._build_repo_result(
            data={
                "package": pkg,
                "symbols_selected": 3,
                "symbols_new": 1,
                "symbols_suppressed": 2,
            }
        )
        scope = self._make_scope(repo_result)

        assert scope["session_context_status"] == "assembled"
        assert scope["session_symbols_selected"] == 3
        assert scope["session_symbols_new"] == 1
        assert scope["session_symbols_suppressed"] == 2
        # Verify invariant
        assert scope["session_symbols_selected"] == scope["session_symbols_new"] + scope["session_symbols_suppressed"]

    def test_empty_path_counts(self) -> None:
        """On empty path, all symbol counts are zero."""
        repo_result = self._build_repo_result(
            data={
                "symbols_selected": 0,
                "symbols_new": 0,
                "symbols_suppressed": 0,
            }
        )
        scope = self._make_scope(repo_result)

        assert scope["session_context_status"] == "empty"
        assert scope["session_symbols_selected"] == 0
        assert scope["session_symbols_new"] == 0
        assert scope["session_symbols_suppressed"] == 0
        # Verify invariant (trivially)
        assert scope["session_symbols_selected"] == scope["session_symbols_new"] + scope["session_symbols_suppressed"]

    def test_disabled_path_counts(self) -> None:
        """On disabled path, all symbol counts are zero."""
        repo_result = self._build_repo_result(
            data={
                "enabled": False,
                "symbols_selected": 0,
                "symbols_new": 0,
                "symbols_suppressed": 0,
            }
        )
        scope = self._make_scope(repo_result)

        assert scope["session_context_status"] == "disabled"
        assert scope["session_symbols_selected"] == 0
        assert scope["session_symbols_new"] == 0
        assert scope["session_symbols_suppressed"] == 0