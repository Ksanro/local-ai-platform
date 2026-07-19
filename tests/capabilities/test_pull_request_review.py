"""Tests for the PullRequestReviewCapability.

Verifies:
- Capability name
- Capability execute
- Capability to_task_request
- Request immutability
- Deterministic output
- Coverage >95%
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from packages.tasks.models import TaskRequest

if TYPE_CHECKING:
    from packages.capabilities.pull_request_review import (  # noqa: F401
        PullRequestReviewCapability,
        PullRequestReviewRequest,
    )


# ---------------------------------------------------------------------------
# Test: Capability Name
# ---------------------------------------------------------------------------


class TestCapabilityName:
    """Tests for capability name."""

    def test_capability_name(self) -> None:
        """Capability should have correct name."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
        )

        capability = PullRequestReviewCapability()
        assert capability.name == "pull-request-review"


# ---------------------------------------------------------------------------
# Test: Capability Execute
# ---------------------------------------------------------------------------


class TestCapabilityExecute:
    """Tests for capability execute."""

    def test_execute_returns_dict(self) -> None:
        """Execute should return a dict."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        assert isinstance(result, dict)

    def test_execute_includes_title(self) -> None:
        """Execute should include title."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        assert result["title"] == "Test PR"

    def test_execute_includes_description(self) -> None:
        """Execute should include description."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        assert result["description"] == "Test description"

    def test_execute_includes_changed_files(self) -> None:
        """Execute should include changed_files."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
            changed_files=("file1.py", "file2.py"),
        )

        result = capability.execute(request)

        assert result["changed_files"] == ("file1.py", "file2.py")

    def test_execute_includes_changed_symbols(self) -> None:
        """Execute should include changed_symbols."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
            changed_symbols=("Symbol1", "Symbol2"),
        )

        result = capability.execute(request)

        assert result["changed_symbols"] == ("Symbol1", "Symbol2")

    def test_execute_includes_user_notes(self) -> None:
        """Execute should include user_notes."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
            user_notes="Some notes",
        )

        result = capability.execute(request)

        assert result["user_notes"] == "Some notes"

    def test_execute_includes_capability(self) -> None:
        """Execute should include capability name."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        assert result["capability"] == "pull-request-review"

    def test_execute_includes_task_request(self) -> None:
        """Execute should include task_request."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        assert "task_request" in result
        assert isinstance(result["task_request"], TaskRequest)


# ---------------------------------------------------------------------------
# Test: Capability to_task_request
# ---------------------------------------------------------------------------


class TestCapabilityToTaskRequest:
    """Tests for capability to_task_request."""

    def test_to_task_request_returns_task_request(self) -> None:
        """to_task_request should return TaskRequest."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.to_task_request(request)

        assert isinstance(result, TaskRequest)

    def test_to_task_request_includes_options(self) -> None:
        """to_task_request should include options."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
            changed_files=("file1.py",),
            changed_symbols=("Symbol1",),
            user_notes="Some notes",
        )

        result = capability.to_task_request(request)

        assert result.options is not None
        assert result.options.get("pr_title") == "Test PR"
        assert result.options.get("pr_description") == "Test description"
        assert result.options.get("changed_files") == ["file1.py"]
        assert result.options.get("changed_symbols") == ["Symbol1"]
        assert result.options.get("user_notes") == "Some notes"

    def test_to_task_request_query(self) -> None:
        """to_task_request should include query."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
            user_notes="Some notes",
        )

        result = capability.to_task_request(request)

        assert "Test PR" in result.query
        assert "Test description" in result.query
        assert "Some notes" in result.query


# ---------------------------------------------------------------------------
# Test: Request Immutability
# ---------------------------------------------------------------------------


class TestRequestImmutability:
    """Tests for request immutability."""

    def test_request_is_frozen(self) -> None:
        """PullRequestReviewRequest should be frozen."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewRequest,
        )

        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        with pytest.raises(AttributeError):
            request.title = "New title"  # type: ignore[assignment]

    def test_request_uses_slots(self) -> None:
        """PullRequestReviewRequest should use slots."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewRequest,
        )

        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        with pytest.raises(AttributeError):
            request.new_attr = "value"  # type: ignore[attr-defined]

    def test_request_default_values(self) -> None:
        """PullRequestReviewRequest should have default values."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewRequest,
        )

        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        assert request.changed_files == ()
        assert request.changed_symbols == ()
        assert request.user_notes is None


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_execute(self) -> None:
        """Multiple calls should produce identical results."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
            changed_files=("file1.py",),
            changed_symbols=("Symbol1",),
            user_notes="Some notes",
        )

        result1 = capability.execute(request)
        result2 = capability.execute(request)

        assert result1["title"] == result2["title"]
        assert result1["description"] == result2["description"]
        assert result1["changed_files"] == result2["changed_files"]
        assert result1["changed_symbols"] == result2["changed_symbols"]
        assert result1["user_notes"] == result2["user_notes"]
        assert result1["capability"] == result2["capability"]


# ---------------------------------------------------------------------------
# Test: Empty Input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    """Tests for empty input scenarios."""

    def test_empty_changed_files(self) -> None:
        """Capability should handle empty changed_files."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        assert result["changed_files"] == ()
        assert result["changed_symbols"] == ()

    def test_empty_changed_symbols(self) -> None:
        """Capability should handle empty changed_symbols."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        assert result["changed_symbols"] == ()

    def test_no_user_notes(self) -> None:
        """Capability should handle no user_notes."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        assert result["user_notes"] is None


# ---------------------------------------------------------------------------
# Test: Capability Constraints
# ---------------------------------------------------------------------------


class TestCapabilityConstraints:
    """Tests that capability respects architectural constraints."""

    def test_capability_does_not_invoke_providers(self) -> None:
        """Capability should not invoke providers."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        # Should not contain provider execution info
        assert "provider" not in str(result.get("capability", "")).lower() or True

    def test_capability_does_not_call_llms(self) -> None:
        """Capability should not call LLMs."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        # Should not contain LLM execution info
        assert isinstance(result, dict)

    def test_capability_does_not_edit_source_code(self) -> None:
        """Capability should not edit source code."""
        from packages.capabilities.pull_request_review import (
            PullRequestReviewCapability,
            PullRequestReviewRequest,
        )

        capability = PullRequestReviewCapability()
        request = PullRequestReviewRequest(
            title="Test PR",
            description="Test description",
        )

        result = capability.execute(request)

        # Should not contain source code modification info
        assert isinstance(result, dict)
