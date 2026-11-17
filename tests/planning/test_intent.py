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


class TestActionableExplainCollision:
    """Actionable work named before an explanation request keeps its intent.

    EXPLAIN is first in the keyword priority order, so a prompt that asks for
    work to be done and then for an explanation used to be classified EXPLAIN.
    These cases pin the bounded rule that resolves that collision, and the
    prompts it must leave alone.
    """

    def test_implement_with_explain_is_implement(self):
        """'implement X and explain the change' is an implementation task."""
        match = Intent.detect_match(
            ["Implement a retry field in the provider client and explain the change."]
        )

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "implement"

    def test_modify_files_with_explain_is_implement(self):
        """'modify files and explain why' is an implementation task."""
        match = Intent.detect_match(["Modify the files under packages/context and explain why."])

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "modify"

    def test_add_then_explain_is_implement(self):
        """'add X, then explain it' is an implementation task."""
        match = Intent.detect_match(["Add streaming to the gateway, then explain it."])

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "add"

    def test_explain_how_implemented_is_explain(self):
        """A question about an implementation stays EXPLAIN."""
        assert (
            Intent.detect(["Explain how retry is implemented in the provider."]) == Intent.EXPLAIN
        )

    def test_explain_architecture_is_explain(self):
        """A pure explanation request stays EXPLAIN."""
        assert Intent.detect(["Explain the architecture."]) == Intent.EXPLAIN

    def test_fix_with_explain_is_debug(self):
        """'fix the error and explain the cause' stays a debug task."""
        match = Intent.detect_match(["Fix the error and explain the cause."])

        assert match.intent == Intent.DEBUG
        assert match.keyword == "fix"

    def test_refactor_with_explain_is_refactor(self):
        """'refactor X and explain the result' stays a refactor task."""
        match = Intent.detect_match(["Refactor session logging and explain the result."])

        assert match.intent == Intent.REFACTOR
        assert match.keyword == "refactor"

    def test_explain_then_add_is_implement(self):
        """A mutation sequenced after the explanation is still work to do.

        Reverses the guard this class used to hold for that shape: requirement 5
        states it as an action request, and it is decided by the sequencer
        pattern, not by the position of the verb alone.
        """
        match = Intent.detect_match(["Explain this, then add tests."])

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "add"

    def test_explanation_with_a_noun_after_it_stays_explain(self):
        """An action word after the question, with no sequencer, does not move it."""
        assert (
            Intent.detect(["Explain how retry is implemented in the provider."]) == Intent.EXPLAIN
        )

    def test_interrogative_with_action_verb_stays_explain(self):
        """'how do I add X' is a question, not a task."""
        assert Intent.detect(["How do I add a provider?"]) == Intent.EXPLAIN

    def test_negated_action_before_explain_stays_explain(self):
        """A removed negative command leaves the explanation in charge."""
        assert Intent.detect(["Do not add anything, just explain the flow."]) == Intent.EXPLAIN

    def test_do_not_modify_files_prompt_stays_explain(self):
        """Read-only investigation wording keeps EXPLAIN.

        Same shape as a real Cline prompt: the action verbs sit after the
        explanation request, so nothing overrides it.
        """
        messages = [
            (
                "Explain investigation only. Do not modify files. "
                "Add a note about how the tests run later."
            )
        ]
        assert Intent.detect(messages) == Intent.EXPLAIN

    def test_custom_rule_beats_action_collision(self):
        """Configured rules keep precedence over the collision rule."""
        match = Intent.detect_match(
            ["Add a health field and explain the flow"],
            custom_rules={"EXPLAIN": ("health",)},
        )

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "custom:health"

    def test_action_in_older_message_does_not_override_newer_explain(self):
        """A marker in an older turn cannot reprice the newest user's request.

        Replaces `test_action_marker_works_across_messages`, which pinned the
        regression: detection reads the newest user message alone when that
        message is classifiable on its own.
        """
        match = Intent.detect_match(
            ["Add a health field to /v1/models.", "Explain what you changed."]
        )

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "explain"

    def test_default_followup_inherits_earlier_action_intent(self):
        """A follow-up with no signal of its own keeps the conversation's intent."""
        match = Intent.detect_match(
            ["Add a health field to /v1/models.", "Same for the other file."]
        )

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "add"

    def test_earliest_action_marker_decides(self):
        """The first verb states the task when several precede the question."""
        match = Intent.detect_match(["Fix the failing replay, then add a probe and explain both."])

        assert match.intent == Intent.DEBUG
        assert match.keyword == "fix"


class TestSequencedActionAfterExplanation:
    """A mutation sequenced after an explanation request keeps its own intent.

    The second branch of the collision rule: the question comes first, but the
    prompt still orders a change to the repository. The shape is bounded to a
    sequencing word immediately followed by an action verb, so questions that
    merely contain an action word stay EXPLAIN.
    """

    def test_explain_then_fix_is_debug(self):
        """'explain the failure, then fix the parser' is a debug task."""
        match = Intent.detect_match(["Explain the failure, then fix the parser."])

        assert match.intent == Intent.DEBUG
        assert match.keyword == "fix"

    def test_explain_then_add_is_implement(self):
        """'explain the current flow, then add retry support' is implementation."""
        match = Intent.detect_match(["Explain the current flow, then add retry support."])

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "add"

    def test_explain_then_refactor_is_refactor(self):
        """A sequenced restructure instruction stays a refactor task."""
        match = Intent.detect_match(["Explain the module, then refactor the helpers."])

        assert match.intent == Intent.REFACTOR
        assert match.keyword == "refactor"

    def test_interrogative_with_action_verb_stays_explain(self):
        """'how do I add X' carries no sequenced instruction."""
        assert Intent.detect(["How do I add a provider?"]) == Intent.EXPLAIN

    def test_question_after_the_sequencer_stays_explain(self):
        """A sequencer followed by a question, not a verb, stays EXPLAIN."""
        assert Intent.detect(["Explain it, then how do I add a provider?"]) == Intent.EXPLAIN

    def test_word_next_without_a_sequenced_verb_stays_explain(self):
        """'next' used as an adverb does not order work."""
        assert Intent.detect(["Explain what the code does next."]) == Intent.EXPLAIN
        assert Intent.detect(["What happens next, explain the flow."]) == Intent.EXPLAIN

    def test_third_person_verb_after_the_sequencer_does_not_match(self):
        """Whole-word matching still applies to the sequenced verb."""
        assert Intent.detect(["Explain the flow, then it adds a symbol."]) == Intent.EXPLAIN

    def test_sequenced_verb_with_an_empty_object_still_reads_as_action(self):
        """Known cost of the bounded pattern: the verb counts, its object does not."""
        assert Intent.detect(["Explain the flow, then add nothing."]) == Intent.IMPLEMENT

    def test_custom_rule_beats_sequenced_action(self):
        """Configured rules keep precedence over the sequenced branch too."""
        match = Intent.detect_match(
            ["Explain the current flow, then add retry support."],
            custom_rules={"EXPLAIN": ("flow",)},
        )

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "custom:flow"


class TestQuestionSentencesInCollision:
    """A verb inside a question the prompt asks is not an instruction it gives.

    The collision rule reads work named before an explanation request as that work,
    which is right for "add a retry field and explain it" and wrong for "where do we
    add providers? explain briefly" - there the verb sits in a sentence the requester
    is wondering out loud in, and the only thing asked for is an explanation. A
    question that opens by addressing the reader is a request wearing question
    clothing, so its verb counts again, and a sequenced verb written as a label
    ("Next fix: none needed.") orders nothing.
    """

    def test_question_before_explain_is_explain(self):
        """'Where do we add X? Explain.' asks where, it does not ask to add."""
        match = Intent.detect_match(
            ["Where do we add new providers in the registry? Explain briefly."]
        )

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "explain"

    def test_question_with_fix_before_explain_is_explain(self):
        """'What should I fix first? Explain.' keeps the debug verb in the question."""
        match = Intent.detect_match(["What should I fix first? Explain."])

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "explain"

    def test_yes_no_question_with_create_before_explain_is_explain(self):
        """A yes/no question contributes no action marker either."""
        match = Intent.detect_match(
            ["Does the gateway create a new index per request? Please explain."]
        )

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "explain"

    def test_why_question_with_add_before_explain_is_explain(self):
        """'Why do we add X? Explain.' asks about a decision already taken."""
        match = Intent.detect_match(["Why do we add the import block? Explain."])

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "explain"

    def test_action_verb_written_as_a_label_is_explain(self):
        """'Explain the diff. Next fix: none needed.' names a slot, not work."""
        match = Intent.detect_match(["Explain the diff. Next fix: none needed."])

        assert match.intent == Intent.EXPLAIN
        assert match.keyword == "explain"

    def test_request_question_still_counts_as_the_action(self):
        """'Can you add X and explain it?' is a request wearing question clothing."""
        match = Intent.detect_match(["Can you add a retry field and explain it?"])

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "add"

    def test_every_request_opener_keeps_a_question_actionable(self):
        """All five openings exempt the question, not just the one above."""
        for opener in ("can you", "could you", "would you", "will you", "please"):
            text = f"{opener} add a retry field and explain it?"
            assert Intent.detect([text]) == Intent.IMPLEMENT, text

    def test_file_name_in_question_does_not_end_the_sentence(self):
        """The dot in 'registry.py' is not a sentence end, so the '?' still closes it."""
        for text in (
            "Where do we add providers in registry.py? Explain briefly.",
            "Why do we create the index in main.py? Explain.",
            "What should I fix in packages/planning/intent.py first? Explain.",
        ):
            match = Intent.detect_match([text])
            assert match.intent == Intent.EXPLAIN, text
            assert match.keyword == "explain", text

    def test_file_name_in_request_question_still_counts_as_the_action(self):
        """A request opener before a file name keeps the question actionable."""
        match = Intent.detect_match(["Can you add a retry field to config.py and explain it?"])

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "add"

    def test_file_name_in_statement_is_still_the_action(self):
        """An instruction naming a file is still an instruction."""
        match = Intent.detect_match(["Add a retry field to config.py. Explain the change."])

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "add"

    def test_question_with_no_explain_keyword_is_untouched(self):
        """The boundary of this rule, pinned as documentation.

        'Why does the builder add the import block?' carries no EXPLAIN keyword, so
        the collision rule never runs on it and the keyword table decides: IMPLEMENT
        on 'add', at c4dfac6, at 7cb03b4 and here. Question handling was fixed inside
        the collision rule only; general question classification is unchanged.
        """
        match = Intent.detect_match(["Why does the builder add the import block?"])

        assert match.intent == Intent.IMPLEMENT
        assert match.keyword == "add"


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
