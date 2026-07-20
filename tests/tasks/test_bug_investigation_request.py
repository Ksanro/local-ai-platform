"""Tests for the BugInvestigationRequest model.

Verifies:
- Immutable model (frozen=True)
- title is required
- All optional fields default to empty
- to_task_request() produces correct TaskRequest
- Deterministic output
- Coverage >95%
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Test: Immutable Model
# ---------------------------------------------------------------------------


class TestImmutableModel:
    """Tests for BugInvestigationRequest immutability."""

    def test_model_is_frozen(self) -> None:
        """BugInvestigationRequest should be immutable."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test bug")

        with pytest.raises(Exception):  # FrozenInstanceError
            request.title = "Modified"

    def test_model_has_slots(self) -> None:
        """BugInvestigationRequest should use slots."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test bug")

        # slots=True means no __dict__ for attribute storage
        assert not hasattr(request, "__dict__") or all(
            k in {"title", "description", "observed_behavior", "expected_behavior",
                  "changed_files", "changed_symbols", "stack_trace", "logs", "tags"}
            for k in dir(request) if not k.startswith("_")
        )


# ---------------------------------------------------------------------------
# Test: Required Field
# ---------------------------------------------------------------------------


class TestRequiredField:
    """Tests for required title field."""

    def test_title_is_required(self) -> None:
        """BugInvestigationRequest requires title."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        with pytest.raises(TypeError):
            BugInvestigationRequest()  # type: ignore[call-arg]

    def test_title_can_be_empty(self) -> None:
        """Title can be empty string."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="")
        assert request.title == ""


# ---------------------------------------------------------------------------
# Test: Default Values
# ---------------------------------------------------------------------------


class TestDefaultValues:
    """Tests for default field values."""

    def test_description_defaults_to_empty(self) -> None:
        """description should default to empty string."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        assert request.description == ""

    def test_observed_behavior_defaults_to_empty(self) -> None:
        """observed_behavior should default to empty string."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        assert request.observed_behavior == ""

    def test_expected_behavior_defaults_to_empty(self) -> None:
        """expected_behavior should default to empty string."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        assert request.expected_behavior == ""

    def test_changed_files_defaults_to_empty_tuple(self) -> None:
        """changed_files should default to empty tuple."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        assert request.changed_files == ()
        assert isinstance(request.changed_files, tuple)

    def test_changed_symbols_defaults_to_empty_tuple(self) -> None:
        """changed_symbols should default to empty tuple."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        assert request.changed_symbols == ()
        assert isinstance(request.changed_symbols, tuple)

    def test_stack_trace_defaults_to_none(self) -> None:
        """stack_trace should default to None."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        assert request.stack_trace is None

    def test_logs_defaults_to_empty_tuple(self) -> None:
        """logs should default to empty tuple."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        assert request.logs == ()
        assert isinstance(request.logs, tuple)

    def test_tags_defaults_to_empty_tuple(self) -> None:
        """tags should default to empty tuple."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        assert request.tags == ()
        assert isinstance(request.tags, tuple)


# ---------------------------------------------------------------------------
# Test: Full Construction
# ---------------------------------------------------------------------------


class TestFullConstruction:
    """Tests for full request construction."""

    def test_full_construction(self) -> None:
        """BugInvestigationRequest should accept all fields."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Auth fails on timeout",
            description="Authentication fails when session expires",
            observed_behavior="TimeoutError after 30s",
            expected_behavior="Successful authentication",
            changed_files=("packages/auth/auth.py", "packages/session/session.py"),
            changed_symbols=("authenticate", "validate_session"),
            stack_trace="TimeoutError at line 42",
            logs=("ERROR: timeout", "WARN: session expired"),
            tags=("auth", "timeout", "session"),
        )

        assert request.title == "Auth fails on timeout"
        assert request.description == "Authentication fails when session expires"
        assert request.observed_behavior == "TimeoutError after 30s"
        assert request.expected_behavior == "Successful authentication"
        assert request.changed_files == ("packages/auth/auth.py", "packages/session/session.py")
        assert request.changed_symbols == ("authenticate", "validate_session")
        assert request.stack_trace == "TimeoutError at line 42"
        assert request.logs == ("ERROR: timeout", "WARN: session expired")
        assert request.tags == ("auth", "timeout", "session")

    def test_all_fields_are_tuples(self) -> None:
        """Tuple fields should be tuples."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            changed_files=("a.py",),
            changed_symbols=("foo",),
            logs=("log",),
            tags=("tag",),
        )

        assert isinstance(request.changed_files, tuple)
        assert isinstance(request.changed_symbols, tuple)
        assert isinstance(request.logs, tuple)
        assert isinstance(request.tags, tuple)


# ---------------------------------------------------------------------------
# Test: to_task_request()
# ---------------------------------------------------------------------------


class TestToTaskRequest:
    """Tests for to_task_request() method."""

    def test_produces_task_request(self) -> None:
        """to_task_request should produce a TaskRequest."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest
        from packages.tasks.models import TaskRequest

        request = BugInvestigationRequest(title="Test bug")
        task_request = request.to_task_request()

        assert isinstance(task_request, TaskRequest)

    def test_query_from_title(self) -> None:
        """query should contain the title."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Auth fails on timeout")
        task_request = request.to_task_request()

        assert "Auth fails on timeout" in task_request.query

    def test_query_includes_description(self) -> None:
        """query should include the description."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Auth fails",
            description="Authentication fails on timeout",
        )
        task_request = request.to_task_request()

        assert "Authentication fails on timeout" in task_request.query

    def test_repository_root_is_dot(self) -> None:
        """repository_root should be '.'."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        task_request = request.to_task_request()

        assert task_request.repository_root == "."

    def test_options_contains_changed_files(self) -> None:
        """options should contain changed_files."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            changed_files=("a.py", "b.py"),
        )
        task_request = request.to_task_request()

        assert "changed_files" in task_request.options
        assert "a.py" in task_request.options["changed_files"]
        assert "b.py" in task_request.options["changed_files"]

    def test_options_contains_changed_symbols(self) -> None:
        """options should contain changed_symbols."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            changed_symbols=("authenticate", "validate"),
        )
        task_request = request.to_task_request()

        assert "changed_symbols" in task_request.options
        assert "authenticate" in task_request.options["changed_symbols"]
        assert "validate" in task_request.options["changed_symbols"]

    def test_options_contains_stack_trace(self) -> None:
        """options should contain stack_trace when provided."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            stack_trace="TimeoutError at line 42",
        )
        task_request = request.to_task_request()

        assert "stack_trace" in task_request.options
        assert task_request.options["stack_trace"] == "TimeoutError at line 42"

    def test_options_excludes_none_stack_trace(self) -> None:
        """options should not contain stack_trace when None."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        task_request = request.to_task_request()

        assert "stack_trace" not in task_request.options

    def test_options_contains_logs(self) -> None:
        """options should contain logs when provided."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            logs=("ERROR: timeout", "WARN: expired"),
        )
        task_request = request.to_task_request()

        assert "logs" in task_request.options
        assert "ERROR: timeout" in task_request.options["logs"]

    def test_options_excludes_empty_logs(self) -> None:
        """options should not contain logs when empty."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        task_request = request.to_task_request()

        assert "logs" not in task_request.options

    def test_options_contains_tags(self) -> None:
        """options should contain tags when provided."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            tags=("auth", "timeout"),
        )
        task_request = request.to_task_request()

        assert "tags" in task_request.options
        assert "auth" in task_request.options["tags"]
        assert "timeout" in task_request.options["tags"]

    def test_options_excludes_empty_tags(self) -> None:
        """options should not contain tags when empty."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test")
        task_request = request.to_task_request()

        assert "tags" not in task_request.options

    def test_user_messages_with_description(self) -> None:
        """user_messages should include title and description."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Title",
            description="Description",
        )
        task_request = request.to_task_request()

        assert task_request.user_messages == ("Title", "Description")

    def test_user_messages_without_description(self) -> None:
        """user_messages should only include title when no description."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Title")
        task_request = request.to_task_request()

        assert task_request.user_messages == ("Title",)


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_request(self) -> None:
        """Multiple constructions should produce identical requests."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request1 = BugInvestigationRequest(
            title="Test",
            description="Desc",
            observed_behavior="Obs",
            expected_behavior="Exp",
            changed_files=("a.py",),
            changed_symbols=("foo",),
            stack_trace="trace",
            logs=("log",),
            tags=("tag",),
        )
        request2 = BugInvestigationRequest(
            title="Test",
            description="Desc",
            observed_behavior="Obs",
            expected_behavior="Exp",
            changed_files=("a.py",),
            changed_symbols=("foo",),
            stack_trace="trace",
            logs=("log",),
            tags=("tag",),
        )

        assert request1.title == request2.title
        assert request1.description == request2.description
        assert request1.changed_files == request2.changed_files
        assert request1.changed_symbols == request2.changed_symbols
        assert request1.stack_trace == request2.stack_trace
        assert request1.logs == request2.logs
        assert request1.tags == request2.tags

    def test_deterministic_task_request(self) -> None:
        """to_task_request should produce identical TaskRequests."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            description="Desc",
            changed_files=("a.py",),
            changed_symbols=("foo",),
            stack_trace="trace",
            logs=("log",),
            tags=("tag",),
        )

        task_request1 = request.to_task_request()
        task_request2 = request.to_task_request()

        assert task_request1.query == task_request2.query
        assert task_request1.options == task_request2.options
        assert task_request1.user_messages == task_request2.user_messages


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_query(self) -> None:
        """to_task_request should handle empty query."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="")
        task_request = request.to_task_request()

        assert task_request.query == ""

    def test_long_title(self) -> None:
        """to_task_request should handle long titles."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        long_title = "A" * 10000
        request = BugInvestigationRequest(title=long_title)
        task_request = request.to_task_request()

        assert task_request.query == long_title

    def test_special_characters(self) -> None:
        """to_task_request should handle special characters."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test with special chars: !@#$%^&*()"
        )
        task_request = request.to_task_request()

        assert "Test with special chars: !@#$%^&*()" in task_request.query

    def test_unicode(self) -> None:
        """to_task_request should handle unicode."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(title="Test with unicode: 你好世界")
        task_request = request.to_task_request()

        assert "你好世界" in task_request.query

    def test_newlines(self) -> None:
        """to_task_request should handle newlines."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test\nwith\nnewlines"
        )
        task_request = request.to_task_request()

        assert "\n" in task_request.query

    def test_single_file(self) -> None:
        """to_task_request should handle single file."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            changed_files=("single.py",),
        )
        task_request = request.to_task_request()

        assert task_request.options["changed_files"] == ["single.py"]

    def test_single_symbol(self) -> None:
        """to_task_request should handle single symbol."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        request = BugInvestigationRequest(
            title="Test",
            changed_symbols=("single",),
        )
        task_request = request.to_task_request()

        assert task_request.options["changed_symbols"] == ["single"]