"""Tests for the OpenAI serializer.

Verifies message formatting, ordering, determinism, and edge cases.
"""

from __future__ import annotations

import pytest

from packages.context.context_package import ContextMetadata, ContextPackage
from packages.serializers.exceptions import SerializationFormatError
from packages.serializers.models import ProviderRequest
from packages.serializers.openai import OpenAISerializer
from packages.serializers.types import ProviderType


class TestOpenAISerializer:
    """Tests for OpenAISerializer."""

    @pytest.fixture
    def serializer(self) -> OpenAISerializer:
        """Provide a fresh OpenAISerializer instance."""
        return OpenAISerializer()

    def test_provider_type(self, serializer: OpenAISerializer) -> None:
        """Verify the serializer targets the correct provider type."""
        assert serializer.provider == ProviderType.openai

    def test_serialize_basic_user_message(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify basic serialization of a single user message."""
        messages = [{"role": "user", "content": "Hello"}]
        result = serializer.serialize(None, messages)

        assert isinstance(result, ProviderRequest)
        assert result.provider_type == ProviderType.openai
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "user"
        assert result.messages[0]["content"] == "Hello"

    def test_serialize_multiple_messages(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify serialization preserves message order and roles."""
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
            {"role": "user", "content": "Give me an example."},
        ]
        result = serializer.serialize(None, messages)

        assert len(result.messages) == 3
        assert result.messages[0]["role"] == "user"
        assert result.messages[0]["content"] == "What is Python?"
        assert result.messages[1]["role"] == "assistant"
        assert result.messages[1]["content"] == "Python is a programming language."
        assert result.messages[2]["role"] == "user"
        assert result.messages[2]["content"] == "Give me an example."

    def test_serialize_with_context_package(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify repository context is included when symbols are present."""
        context_package = ContextPackage(
            primary_symbol="auth.AuthenticationMiddleware",
            supporting_symbols=["main.App"],
            related_callers=["main.create_app"],
            related_callees=["auth.Token.create"],
            related_modules=["auth.py", "main.py"],
            metadata=ContextMetadata(estimated_tokens=230),
        )
        messages = [{"role": "user", "content": "How does auth work?"}]

        result = serializer.serialize(context_package, messages)

        # Should have: system message + repo context + user message
        assert len(result.messages) == 3
        assert result.messages[0]["role"] == "system"
        assert result.messages[1]["role"] == "user"
        assert "Primary symbol:" in result.messages[1]["content"]
        assert "auth.AuthenticationMiddleware" in result.messages[1]["content"]
        assert "Related modules:" in result.messages[1]["content"]
        assert result.messages[2]["role"] == "user"
        assert result.messages[2]["content"] == "How does auth work?"

    def test_serialize_empty_context_package(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify empty context package omits repository context."""
        context_package = ContextPackage()
        messages = [{"role": "user", "content": "Hello"}]

        result = serializer.serialize(context_package, messages)

        # Should have: system message + user message (no repo context)
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "system"
        assert result.messages[1]["role"] == "user"
        assert result.messages[1]["content"] == "Hello"

    def test_serialize_none_context_package(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify None context package omits system and repository context."""
        messages = [{"role": "user", "content": "Hello"}]

        result = serializer.serialize(None, messages)

        # No system message and no repo context when context_package is None
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "user"
        assert result.messages[0]["content"] == "Hello"

    def test_serialize_empty_messages_raises(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify empty messages list raises SerializationFormatError."""
        with pytest.raises(SerializationFormatError):
            serializer.serialize(None, [])

    def test_serialize_invalid_message_raises(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify invalid message structure raises SerializationFormatError."""
        with pytest.raises(SerializationFormatError):
            serializer.serialize(None, [{"role": "user"}])

    def test_serialize_invalid_role_raises(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify invalid role raises SerializationFormatError."""
        with pytest.raises(SerializationFormatError):
            serializer.serialize(None, [{"role": "invalid", "content": "test"}])

    def test_serialize_non_dict_message_raises(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify non-dict message raises SerializationFormatError."""
        with pytest.raises(SerializationFormatError):
            serializer.serialize(None, ["not a dict"])  # type: ignore[list-item]

    def test_user_messages_unchanged(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify user messages are copied unchanged."""
        original_messages = [
            {"role": "user", "content": "Original content"},
            {"role": "assistant", "content": "Assistant reply"},
            {"role": "user", "content": "Follow-up question"},
        ]
        result = serializer.serialize(None, original_messages)

        # User and assistant messages should be preserved exactly
        user_assistant_msgs = [
            m for m in result.messages if m["role"] in ("user", "assistant")
        ]
        assert len(user_assistant_msgs) == 3
        assert user_assistant_msgs[0]["content"] == "Original content"
        assert user_assistant_msgs[1]["content"] == "Assistant reply"
        assert user_assistant_msgs[2]["content"] == "Follow-up question"

    def test_deterministic_serialization(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify serialization is deterministic — identical input produces identical output."""
        context_package = ContextPackage(
            primary_symbol="A",
            supporting_symbols=["B"],
            related_modules=["a.py", "b.py"],
        )
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "World"},
        ]

        result1 = serializer.serialize(context_package, messages)
        result2 = serializer.serialize(context_package, messages)

        assert result1.messages == result2.messages
        assert result1.provider_type == result2.provider_type

    def test_no_side_effects(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify serialization has no side effects."""
        context_package = ContextPackage(
            primary_symbol="Test",
            supporting_symbols=[],
            related_modules=["test.py"],
        )
        messages = [{"role": "user", "content": "Test"}]

        # Serialize multiple times — should produce identical results
        results = [serializer.serialize(context_package, messages) for _ in range(3)]

        for result in results:
            assert result.messages == results[0].messages
            assert result.provider_type == ProviderType.openai


class TestOpenAIWithSymbols:
    """Tests for symbol-containing context packages."""

    @pytest.fixture
    def serializer(self) -> OpenAISerializer:
        return OpenAISerializer()

    def test_symbols_included_when_present(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify symbols are included in repository context."""
        context_package = ContextPackage(
            primary_symbol="auth.login",
            supporting_symbols=["auth.authenticate"],
            related_modules=["auth.py"],
        )
        messages = [{"role": "user", "content": "Where is login?"}]

        result = serializer.serialize(context_package, messages)

        repo_msg = result.messages[1]
        assert "Primary symbol:" in repo_msg["content"]
        assert "auth.login" in repo_msg["content"]
        assert "auth.authenticate" in repo_msg["content"]

    def test_modules_included_when_present(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify modules are included in repository context."""
        context_package = ContextPackage(
            primary_symbol="auth.login",
            supporting_symbols=[],
            related_modules=["auth.py", "main.py", "utils.py"],
        )
        messages = [{"role": "user", "content": "Test"}]

        result = serializer.serialize(context_package, messages)

        repo_msg = result.messages[1]
        assert "Related modules:" in repo_msg["content"]
        assert "auth.py" in repo_msg["content"]
        assert "main.py" in repo_msg["content"]
        assert "utils.py" in repo_msg["content"]

    def test_callers_included_when_present(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify callers are included in repository context."""
        context_package = ContextPackage(
            primary_symbol="auth.login",
            supporting_symbols=[],
            related_callers=["main.create_app", "router.register"],
            related_modules=["auth.py"],
        )
        messages = [{"role": "user", "content": "Help"}]

        result = serializer.serialize(context_package, messages)

        repo_msg = result.messages[1]
        assert "Related callers:" in repo_msg["content"]
        assert "main.create_app" in repo_msg["content"]
        assert "router.register" in repo_msg["content"]

    def test_callees_included_when_present(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify callees are included in repository context."""
        context_package = ContextPackage(
            primary_symbol="auth.login",
            supporting_symbols=[],
            related_callees=["auth.Token.create", "auth.JWT.verify"],
            related_modules=["auth.py"],
        )
        messages = [{"role": "user", "content": "Help"}]

        result = serializer.serialize(context_package, messages)

        repo_msg = result.messages[1]
        assert "Related callees:" in repo_msg["content"]
        assert "auth.Token.create" in repo_msg["content"]
        assert "auth.JWT.verify" in repo_msg["content"]


class TestOpenAIEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def serializer(self) -> OpenAISerializer:
        return OpenAISerializer()

    def test_no_symbols_no_context_message(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify no repository context message when symbols are empty."""
        context_package = ContextPackage()
        messages = [{"role": "user", "content": "Hello"}]

        result = serializer.serialize(context_package, messages)

        # Should have: system + user (no repo context)
        # The user message at index 1 should be the original user message
        assert result.messages[-1]["content"] == "Hello"

    def test_only_system_message_no_context(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify only system message when context is empty."""
        context_package = ContextPackage()
        messages = [{"role": "user", "content": "Hello"}]

        result = serializer.serialize(context_package, messages)

        # System message should be present (because context_package is not None)
        assert result.messages[0]["role"] == "system"
        assert result.messages[1]["role"] == "user"

    def test_none_context_no_system_message(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify no system message when context_package is None."""
        messages = [{"role": "user", "content": "Hello"}]

        result = serializer.serialize(None, messages)

        # No system message when context_package is None
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "user"

    def test_preserves_message_order(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify original message order is preserved."""
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
            {"role": "assistant", "content": "Fourth"},
        ]

        result = serializer.serialize(None, messages)

        user_assistant_msgs = [
            m for m in result.messages if m["role"] in ("user", "assistant")
        ]
        contents = [m["content"] for m in user_assistant_msgs]
        assert contents == ["First", "Second", "Third", "Fourth"]

    def test_to_dict(self) -> None:
        """Verify ProviderRequest.to_dict() produces correct output."""
        request = ProviderRequest(
            provider_type=ProviderType.openai,
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4",
            kwargs={"temperature": 0.7},
        )
        result = request.to_dict()

        assert result["messages"] == [{"role": "user", "content": "Hello"}]
        assert result["model"] == "gpt-4"
        assert result["temperature"] == 0.7

    def test_relationship_summary_in_output(
        self, serializer: OpenAISerializer
    ) -> None:
        """Verify relationship summary appears in output."""
        from packages.context.context_package import RelationshipSummary

        context_package = ContextPackage(
            primary_symbol="auth.Auth",
            supporting_symbols=["auth.Helper"],
            related_callers=["main.create_app"],
            related_callees=["auth.Token.create"],
            related_modules=["auth.py", "main.py"],
            relationship_summary=RelationshipSummary(
                caller_count=1,
                callee_count=1,
                module_count=2,
                symbol_count=3,
            ),
        )
        messages = [{"role": "user", "content": "Test"}]

        result = serializer.serialize(context_package, messages)

        repo_msg = result.messages[1]
        assert "Relationship summary:" in repo_msg["content"]
        assert "1 callers" in repo_msg["content"]
        assert "1 callees" in repo_msg["content"]
        assert "2 modules" in repo_msg["content"]
        assert "3 symbols" in repo_msg["content"]

