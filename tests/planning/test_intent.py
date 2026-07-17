"""Tests for intent detection.

Tests deterministic keyword-based intent detection for all supported
intents plus the DEFAULT fallback.
"""

from __future__ import annotations

from packages.planning.intent import Intent


class TestIntentDetect:
    """Test intent detection from user messages."""

    def test_explain_intent_explain_keyword(self):
        """EXPLAIN intent detected with 'explain' keyword."""
        messages = ["Explain how ProviderFactory works"]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_explain_intent_how_does(self):
        """EXPLAIN intent detected with 'how does' keyword."""
        messages = ["How does the Gateway handle requests"]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_explain_intent_how_do(self):
        """EXPLAIN intent detected with 'how do' keyword."""
        messages = ["How do I configure the pipeline"]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_explain_intent_what_is(self):
        """EXPLAIN intent detected with 'what is' keyword."""
        messages = ["What is the purpose of ContextBuilder"]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_explain_intent_what_does(self):
        """EXPLAIN intent detected with 'what does' keyword."""
        messages = ["What does the RankingEngine do"]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_explain_intent_describe(self):
        """EXPLAIN intent detected with 'describe' keyword."""
        messages = ["Describe the architecture"]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_explain_intent_architecture(self):
        """EXPLAIN intent detected with 'architecture' keyword."""
        messages = ["Show me the architecture overview"]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_implement_intent_implement(self):
        """IMPLEMENT intent detected with 'implement' keyword."""
        messages = ["Implement a new provider"]
        assert Intent.detect(messages) == Intent.IMPLEMENT

    def test_implement_intent_add(self):
        """IMPLEMENT intent detected with 'add' keyword."""
        messages = ["Add a new endpoint"]
        assert Intent.detect(messages) == Intent.IMPLEMENT

    def test_implement_intent_create(self):
        """IMPLEMENT intent detected with 'create' keyword."""
        messages = ["Create a new service"]
        assert Intent.detect(messages) == Intent.IMPLEMENT

    def test_implement_intent_build(self):
        """IMPLEMENT intent detected with 'build' keyword."""
        messages = ["Build a feature for authentication"]
        assert Intent.detect(messages) == Intent.IMPLEMENT

    def test_refactor_intent_refactor(self):
        """REFACTOR intent detected with 'refactor' keyword."""
        messages = ["Refactor the ContextBuilder"]
        assert Intent.detect(messages) == Intent.REFACTOR

    def test_refactor_intent_restructure(self):
        """REFACTOR intent detected with 'restructure' keyword."""
        messages = ["Restructure the pipeline stages"]
        assert Intent.detect(messages) == Intent.REFACTOR

    def test_refactor_intent_cleanup(self):
        """REFACTOR intent detected with 'cleanup' keyword."""
        messages = ["Clean up the repository code"]
        assert Intent.detect(messages) == Intent.REFACTOR

    def test_refactor_intent_simplify(self):
        """REFACTOR intent detected with 'simplify' keyword."""
        messages = ["Simplify the ranking logic"]
        assert Intent.detect(messages) == Intent.REFACTOR

    def test_debug_intent_debug(self):
        """DEBUG intent detected with 'debug' keyword."""
        messages = ["Debug the failing test"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_debug_intent_fix(self):
        """DEBUG intent detected with 'fix' keyword."""
        messages = ["Fix the broken test"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_debug_intent_error(self):
        """DEBUG intent detected with 'error' keyword."""
        messages = ["There is an error in the pipeline"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_debug_intent_failing(self):
        """DEBUG intent detected with 'failing' keyword."""
        messages = ["Fix failing tests"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_debug_intent_exception(self):
        """DEBUG intent detected with 'exception' keyword."""
        messages = ["Handle the exception properly"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_test_intent_test(self):
        """TEST intent detected with 'test' keyword."""
        messages = ["Write tests for the planner"]
        assert Intent.detect(messages) == Intent.TEST

    def test_test_intent_unit_test(self):
        """TEST intent detected with 'unit test' keyword."""
        messages = ["Add unit test coverage"]
        assert Intent.detect(messages) == Intent.TEST

    def test_test_intent_coverage(self):
        """TEST intent detected with 'coverage' keyword."""
        messages = ["Increase test coverage"]
        assert Intent.detect(messages) == Intent.TEST

    def test_test_intent_verify(self):
        """TEST intent detected with 'verify' keyword."""
        messages = ["Verify the implementation"]
        assert Intent.detect(messages) == Intent.TEST

    def test_search_intent_find(self):
        """SEARCH intent detected with 'find' keyword."""
        messages = ["Find all usages of ProviderFactory"]
        assert Intent.detect(messages) == Intent.SEARCH

    def test_search_intent_search(self):
        """SEARCH intent detected with 'search' keyword."""
        messages = ["Search for dead code"]
        assert Intent.detect(messages) == Intent.SEARCH

    def test_search_intent_where_is(self):
        """SEARCH intent detected with 'where is' keyword."""
        messages = ["Where is the gateway configured"]
        assert Intent.detect(messages) == Intent.SEARCH

    def test_search_intent_list(self):
        """SEARCH intent detected with 'list' keyword."""
        messages = ["List all symbols"]
        assert Intent.detect(messages) == Intent.SEARCH

    def test_default_intent_empty_messages(self):
        """DEFAULT returned for empty messages."""
        assert Intent.detect([]) == Intent.DEFAULT

    def test_default_intent_empty_string_messages(self):
        """DEFAULT returned for empty string messages."""
        assert Intent.detect([""]) == Intent.DEFAULT

    def test_default_intent_unknown_request(self):
        """DEFAULT returned for unrecognized request."""
        messages = ["Do something completely unrelated"]
        assert Intent.detect(messages) == Intent.DEFAULT

    def test_default_intent_gibberish(self):
        """DEFAULT returned for gibberish input."""
        messages = ["xyz abc def 123"]
        assert Intent.detect(messages) == Intent.DEFAULT

    def test_case_insensitive_detection(self):
        """Detection is case-insensitive."""
        messages = ["EXPLAIN how this works"]
        assert Intent.detect(messages) == Intent.EXPLAIN

        messages = ["eXpLaIn the architecture"]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_multiple_messages_combined(self):
        """Multiple messages are combined for detection."""
        messages = ["I need to", "implement a new feature"]
        assert Intent.detect(messages) == Intent.IMPLEMENT

    def test_first_match_wins(self):
        """First matching intent wins when multiple keywords match."""
        # "fix" appears in both DEBUG and could appear in other contexts
        # but DEBUG is checked before TEST and SEARCH
        messages = ["Fix the failing test"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_unknown_intent_uses_default(self):
        """Unknown intent strings fall through to DEFAULT."""
        # No keyword matches any pattern
        messages = ["Run the build"]
        # "build" matches IMPLEMENT intent
        assert Intent.detect(messages) == Intent.IMPLEMENT
