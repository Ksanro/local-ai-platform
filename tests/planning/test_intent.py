"""Tests for intent detection.

Tests deterministic keyword-based intent detection for all supported
intents plus the DEFAULT fallback. Includes adversarial collision tests
that verify word-boundary matching prevents substring false positives.
"""

from __future__ import annotations

from packages.planning.intent import Intent
from packages.planning.rules import BUILTIN_RULES


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

    def test_explicit_implementation_task_beats_test_requirements(self):
        """Implementation task markers should not be stolen by test requirements."""
        messages = [
            (
                "Implementation task. Modify files if needed. "
                "Add a gateway health field and add focused tests."
            )
        ]
        match = Intent.detect_match(messages)

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "implement"

    def test_negated_modify_files_does_not_force_implementation(self):
        """Do-not-modify instructions should remain available for other intents."""
        messages = [
            "Explain investigation only. Do not modify files. Add tests later.",
        ]
        assert Intent.detect(messages) == Intent.EXPLAIN

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

    def test_refactor_investigation_beats_later_what_is_question(self):
        """Explicit refactor investigations should not be classified as EXPLAIN."""
        messages = [
            (
                "Refactor investigation only. What is the safest refactor plan "
                "for duplicate repository-context files?"
            ),
        ]
        match = Intent.detect_match(messages)

        assert match.intent == Intent.REFACTOR
        assert match.keyword == "refactor"

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
        messages = ["Run the test suite"]
        assert Intent.detect(messages) == Intent.TEST

    def test_test_intent_unit_test(self):
        """TEST intent detected with 'unit test' keyword."""
        messages = ["Run the unit test suite"]
        assert Intent.detect(messages) == Intent.TEST

    def test_test_intent_coverage(self):
        """TEST intent detected with 'coverage' keyword."""
        messages = ["Check test coverage"]
        assert Intent.detect(messages) == Intent.TEST

    def test_test_intent_verify(self):
        """TEST intent detected with 'verify' keyword."""
        messages = ["Verify the test results"]
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

    def test_search_intent_investigate_without_bug_signal(self):
        """Ambiguous investigation wording defaults to SEARCH."""
        messages = [
            "Investigate where session log answer_preview is extracted",
        ]
        assert Intent.detect(messages) == Intent.SEARCH

    def test_search_intent_inspect(self):
        """SEARCH intent detected with ambiguous inspection wording."""
        messages = ["Inspect the provider payload conversion path"]
        assert Intent.detect(messages) == Intent.SEARCH

    def test_validation_prompt_resolve_word_does_not_force_debug(self):
        """Neutral 'resolve to' wording should not be treated as DEBUG."""
        messages = [
            (
                "Implementation validation only. Do not modify files. "
                "Inspect the current code and answer which intent this "
                "kind of prompt should resolve to."
            )
        ]
        match = Intent.detect_match(messages)

        assert match.intent == Intent.SEARCH
        assert match.keyword == "inspect"

    def test_strong_debug_signal_beats_ambiguous_investigate(self):
        """Bug words keep investigation prompts in DEBUG."""
        messages = ["Investigate the failing answer_preview extraction"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_negated_explain_keyword_does_not_override_search(self):
        """Negative instructions should not make SEARCH look like EXPLAIN."""
        messages = [
            (
                "Locate the code that converts a request into a provider payload. "
                "Do not describe repository context serialization."
            ),
        ]
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


class TestWordBoundaryMatching:
    """Test that word-boundary matching prevents substring false positives."""

    def test_work_not_in_framework(self):
        """'work' keyword should NOT match 'framework'."""
        messages = ["Configure the network framework"]
        # "framework" contains "work" as substring but should not match
        # Since "configure" doesn't match any intent, should fall through
        assert Intent.detect(messages) == Intent.DEFAULT

    def test_work_not_in_workspace(self):
        """'work' keyword should NOT match 'workspace'."""
        messages = ["Navigate to the workspace directory"]
        assert Intent.detect(messages) == Intent.DEFAULT

    def test_work_not_in_network(self):
        """Generic flow wording should not trigger EXPLAIN."""
        messages = ["The network flow is slow"]
        assert Intent.detect(messages) == Intent.DEFAULT

    def test_function_not_in_functionality(self):
        """'function' keyword should NOT match 'functionality'."""
        messages = ["Add new functionality to the module"]
        # "functionality" is an IMPLEMENT keyword (whole word)
        # "function" as substring of "functionality" should not match
        assert Intent.detect(messages) == Intent.IMPLEMENT

    def test_fix_not_in_fixed(self):
        """'fix' keyword should match 'fix' but not 'fixed'."""
        messages = ["The code is fixed now"]
        # "fixed" contains "fix" but word-boundary matching should not match
        assert Intent.detect(messages) == Intent.DEFAULT

    def test_test_not_in_testing(self):
        """'test' keyword should match 'test' but not 'testing'."""
        messages = ["Start testing the module"]
        # "testing" contains "test" but word-boundary matching should not match
        assert Intent.detect(messages) == Intent.DEFAULT

    def test_build_not_in_builder(self):
        """'build' keyword should NOT match 'builder'."""
        messages = ["Refactor the ContextBuilder class"]
        # "builder" contains "build" but word-boundary matching should not match
        # "refactor" should match REFACTOR
        assert Intent.detect(messages) == Intent.REFACTOR

    def test_list_not_in_listed(self):
        """'list' keyword should match 'list' but not 'listed'."""
        messages = ["The items are listed already"]
        assert Intent.detect(messages) == Intent.DEFAULT


class TestAdversarialCollision:
    """Test adversarial multi-intent messages that trigger collision detection."""

    def test_debug_with_function_keyword(self):
        """Generic code nouns should not override DEBUG keywords."""
        messages = ["the auth function is broken, fix it"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_debug_with_work_keyword(self):
        """Generic 'work' wording should not override DEBUG keywords."""
        messages = ["the tests don't work, fix them"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_pure_debug_no_explain_keywords(self):
        """Pure DEBUG message without EXPLAIN keywords should be DEBUG."""
        messages = ["the auth function is broken, fix it now"]
        assert Intent.detect(messages) == Intent.DEBUG

    def test_pure_debug_message(self):
        """Pure DEBUG message should correctly return DEBUG."""
        messages = ["the parser crashes on invalid input, fix the error"]
        # "crash" and "error" are DEBUG keywords, no EXPLAIN keywords
        assert Intent.detect(messages) == Intent.DEBUG

    def test_multi_intent_refactor_with_improve(self):
        """REFACTOR message with 'improve' (also REFACTOR) should be REFACTOR."""
        messages = ["refactor and improve the codebase"]
        # Both "refactor" and "improve" are REFACTOR keywords
        assert Intent.detect(messages) == Intent.REFACTOR

    def test_implementation_with_explain_keywords(self):
        """Generic flow wording should not override IMPLEMENT."""
        messages = ["implement a new feature that explains the flow"]
        assert Intent.detect(messages) == Intent.IMPLEMENT

    def test_detect_match_returns_keyword(self):
        """Detection can report the keyword that selected the intent."""
        match = Intent.detect_match(["Locate session logging"])

        assert match.intent == Intent.SEARCH
        assert match.keyword == "locate"

    def test_custom_rules_can_detect_localized_words(self):
        """Configured rules can classify non-English wording."""
        match = Intent.detect_match(
            ["Te rog adauga configuratia pentru intentii"],
            custom_rules={"IMPLEMENT": ("adauga",)},
        )

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "custom:adauga"

    def test_custom_rules_match_multi_word_phrases(self):
        """Configured multi-word rules use normalized phrase matching."""
        match = Intent.detect_match(
            ["Peux-tu lancer les tests gateway"],
            custom_rules={"TEST": ("lancer les tests",)},
        )

        assert match.intent == Intent.TEST
        assert match.keyword == "custom:lancer les tests"

    def test_custom_rules_beat_builtin_defaults(self):
        """User rules are allowed to override built-in keyword priority."""
        match = Intent.detect_match(
            ["Inspect the code and raspunde succint"],
            custom_rules={"EXPLAIN": ("inspect",)},
        )

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "custom:inspect"

    def test_custom_single_words_do_not_match_substrings(self):
        """Configured single-word rules keep whole-word semantics."""
        assert (
            Intent.detect(
                ["The adaugare path is unrelated"],
                custom_rules={"IMPLEMENT": ("adauga",)},
            )
            == Intent.DEFAULT
        )


class TestExtractWords:
    """Test the _extract_words helper method."""

    def test_extract_words_basic(self):
        """Basic word extraction."""
        words = Intent._extract_words("hello world test")
        assert words == {"hello", "world", "test"}

    def test_extract_words_case_insensitive(self):
        """Word extraction is case-insensitive."""
        words = Intent._extract_words("Hello WORLD Test")
        assert "hello" in words
        assert "world" in words
        assert "test" in words

    def test_extract_words_no_duplicates(self):
        """Duplicate words are deduplicated."""
        words = Intent._extract_words("test test test")
        assert words == {"test"}

    def test_extract_words_ignores_substrings(self):
        """Substrings within words are not extracted as separate words."""
        words = Intent._extract_words("framework workspace builder")
        assert "work" not in words
        assert "build" not in words
        assert "test" not in words
        assert "framework" in words
        assert "workspace" in words
        assert "builder" in words

    def test_extract_words_with_special_chars(self):
        """Hyphens act as word boundaries, underscores do not."""
        # Hyphen splits words, underscore is a word character
        words = Intent._extract_words("hello-world test_case")
        assert "hello" in words
        assert "world" in words
        # test_case is one word (underscore is a word character)
        assert "test_case" in words
        assert "test" not in words  # not a separate word

    def test_extract_words_multi_word_messages(self):
        """Multiple messages are joined before word extraction."""
        words = Intent._extract_words("hello world test case")
        assert words == {"hello", "world", "test", "case"}


class TestIntentRuleAlignment:
    """Test that Intent constants align with BUILTIN_RULES."""

    def test_all_intents_have_rules(self):
        """Every Intent._ALL member has exactly one rule in BUILTIN_RULES."""
        intent_names = set(Intent._ALL)
        rule_intents = {rule.intent for rule in BUILTIN_RULES}
        # Every intent constant must have a corresponding rule
        missing = intent_names - rule_intents
        assert not missing, f"Intents without rules: {missing}"

    def test_no_extra_rules_without_intents(self):
        """Every rule in BUILTIN_RULES has a corresponding Intent member."""
        intent_names = set(Intent._ALL)
        rule_intents = {rule.intent for rule in BUILTIN_RULES}
        # Every rule must correspond to an intent constant
        extra = rule_intents - intent_names
        assert not extra, f"Rules without intent constants: {extra}"

    def test_exactly_one_rule_per_intent(self):
        """Each intent has exactly one rule, not multiple."""
        from collections import Counter
        counts = Counter(rule.intent for rule in BUILTIN_RULES)
        duplicates = {k: v for k, v in counts.items() if v > 1}
        assert not duplicates, f"Intents with multiple rules: {duplicates}"
