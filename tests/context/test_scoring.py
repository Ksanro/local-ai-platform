"""Tests for context scoring module.

Tests covering:
- Query normalisation with stop word removal
- CamelCase decomposition
- Stop word degradation guard (all-stop words query returns original tokens)
- Generic code-discussion word removal
"""

from __future__ import annotations

import pytest

from packages.context.scoring import (
    STOP_WORDS,
    CODE_DISCUSSION_WORDS,
    normalise_query_text,
)


class TestNormaliseQueryTextStopWords:
    """Test stop word removal in normalise_query_text."""

    def test_simple_query_no_stop_words(self):
        """Simple query should contain no stop words."""
        tokens = normalise_query_text("authentication")
        assert "authentication" in tokens
        for sw in STOP_WORDS:
            assert sw not in tokens

    def test_fallback_model_router_query(self):
        """Query with stop words and camelCase should decompose properly."""
        tokens = normalise_query_text("what does FallbackModelRouter.available_models() return?")
        # CamelCase segments should be present
        assert "fallbackmodelrouter" in tokens
        assert "available_models" in tokens
        # Also decomposed camelCase segments
        assert "fallback" in tokens
        assert "model" in tokens
        assert "router" in tokens
        # Stop words should be removed
        assert "what" not in tokens
        assert "does" not in tokens
        assert "return" not in tokens  # 'return' is in CODE_DISCUSSION_WORDS

    def test_pipeline_stage_query(self):
        """Pipeline stage query should not contain stop words or code-discussion words."""
        tokens = normalise_query_text(
            "which pipeline stage runs first, and what does it store on the context?"
        )
        # Core terms should be present
        assert "pipeline" in tokens
        assert "context" in tokens
        # Stop words should be removed
        assert "what" not in tokens
        assert "does" not in tokens
        assert "first" not in tokens  # 'first' is in CODE_DISCUSSION_WORDS
        assert "stage" not in tokens  # 'stage' is in CODE_DISCUSSION_WORDS
        # Code discussion words should be removed
        assert "store" not in tokens  # 'store' is in CODE_DISCUSSION_WORDS


class TestNormaliseQueryTextStopWordLists:
    """Test that stop word lists contain expected words."""

    def test_stop_words_contains_question_words(self):
        """Question words should be in STOP_WORDS."""
        assert "what" in STOP_WORDS
        assert "does" in STOP_WORDS
        assert "which" in STOP_WORDS
        assert "when" in STOP_WORDS
        assert "where" in STOP_WORDS
        assert "why" in STOP_WORDS

    def test_stop_words_contains_common_words(self):
        """Common English words should be in STOP_WORDS."""
        assert "the" in STOP_WORDS
        assert "and" in STOP_WORDS
        assert "is" in STOP_WORDS
        assert "for" in STOP_WORDS
        assert "from" in STOP_WORDS
        assert "with" in STOP_WORDS

    def test_code_discussion_words(self):
        """Generic code-discussion words should be in CODE_DISCUSSION_WORDS."""
        assert "code" in CODE_DISCUSSION_WORDS
        assert "return" in CODE_DISCUSSION_WORDS
        assert "store" in CODE_DISCUSSION_WORDS
        assert "first" in CODE_DISCUSSION_WORDS
        assert "stage" in CODE_DISCUSSION_WORDS


class TestNormaliseQueryTextCamelCase:
    """Test camelCase decomposition."""

    def test_camel_case_decomposition(self):
        """CamelCase names should be decomposed into segments."""
        tokens = normalise_query_text("ModelRouter")
        assert "modelrouter" in tokens
        assert "model" in tokens
        assert "router" in tokens

    def test_camel_case_with_underscore(self):
        """Mixed camelCase and snake_case should be decomposed."""
        tokens = normalise_query_text("FallbackModelRouter.available_models")
        assert "fallbackmodelrouter" in tokens
        assert "fallback" in tokens
        assert "model" in tokens
        assert "router" in tokens
        assert "available_models" in tokens
        assert "available" in tokens
        assert "models" in tokens

    def test_camel_case_with_parens(self):
        """Method calls should be decomposed properly."""
        tokens = normalise_query_text("MyClass.my_method()")
        assert "myclass" in tokens
        assert "my" in tokens
        # "class" and "method" are in CODE_DISCUSSION_WORDS so they are filtered.
        assert "my_method" in tokens

    def test_code_discussion_words_filtered(self):
        """Verify that common code-discussion words are filtered from tokens."""
        tokens = normalise_query_text("MyClass.my_method()")
        # 'class' and 'method' are in CODE_DISCUSSION_WORDS
        assert "class" not in tokens
        assert "method" not in tokens


class TestNormaliseQueryTextDegradation:
    """Test degradation behaviour when all tokens are stop words."""

    def test_all_stop_words_returns_original(self):
        """A query made entirely of stop words should return original tokens."""
        # 'the' and 'is' are both stop words
        tokens = normalise_query_text("the is")
        # Should degrade to original token list
        assert "the" in tokens or "is" in tokens
        # All tokens in result should be from the original
        original_parts = {"the", "is"}
        for t in tokens:
            assert t in original_parts or len(original_parts) == 0

    def test_single_stop_word_returns_original(self):
        """A single stop word query should return the original word."""
        tokens = normalise_query_text("the")
        assert "the" in tokens


class TestNormaliseQueryTextEdgeCases:
    """Test edge cases."""

    def test_empty_query(self):
        """Empty query should return empty list."""
        tokens = normalise_query_text("")
        assert tokens == []

    def test_special_characters_only(self):
        """Special characters should not produce tokens."""
        tokens = normalise_query_text("!!! ???")
        assert tokens == []

    def test_numbers_preserved(self):
        """Numbers should be preserved as tokens."""
        tokens = normalise_query_text("test123 foo")
        assert "test123" in tokens
        assert "foo" in tokens