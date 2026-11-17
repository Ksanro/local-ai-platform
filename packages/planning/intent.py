"""Deterministic intent detection.

Detects user intent from messages using keyword-based rules.
No AI, LLM, embeddings, or inference is performed.

Supported intents
-----------------

EXPLAIN - User wants to understand code or architecture.
REFACTOR - User wants to restructure existing code.
DEBUG - User wants to find or fix bugs.
TEST - User wants to write or run tests.
SEARCH - User wants to find specific information.
IMPLEMENT - User wants to add new functionality.
DEFAULT - Fallback for unrecognized requests.

Detection Rules
---------------

Detection is based on word-boundary matching against user messages.
Keywords are checked as whole-word set membership. A keyword matches
only if it appears as a complete word in the message, not as a
substring of another word (e.g., "work" matches "work" but not
"framework" or "workspace").

Keywords are case-insensitive.

Priority Order
--------------

When multiple intents match (each keyword is a whole word), the
first intent in priority order wins. Priority order prevents false
positives where common coding words appear in symbol names.

EXPLAIN sits first in that order, so a prompt that both asks for work
to be done and asks for an explanation used to be classified EXPLAIN.
One bounded rule, ``_match_action_before_explanation``, resolves that
collision in two shapes: an action marker from ``_ACTION_MARKERS`` that
appears before the first EXPLAIN keyword wins, and otherwise a mutation
instruction sequenced after it ("explain the failure, then fix the
parser", ``_SEQUENCED_ACTION_RE``) wins. The rule is consulted only after
custom rules and the explicit task markers, and only fires on text that
would otherwise be EXPLAIN, so pure questions ("explain how X is
implemented", "how do I add a provider") and prompts without an
explanation request are classified exactly as before.

Neither shape reaches inside a question the prompt is asking. A marker
that sits in a sentence ending in ``?`` does not count unless that
sentence opens by addressing the reader (``_QUESTION_OPENERS``: "can you
add a retry field and explain it?" is a request), because wondering where
work goes is not asking for it to be done; and a sequenced verb written
as a label ("Next fix: none needed.") orders nothing.

Message Order
-------------

Detection is a request-level classification, so which text it reads matters.
The newest non-empty user message is classified alone first; the combined text
of all user messages is used only when the newest message classifies as
DEFAULT. An action marker in an older turn therefore cannot override a newer
request that is independently classifiable ("Add retry support." then "Explain
how repository context currently works. Do not modify files." is EXPLAIN),
while a signal-free follow-up ("Same for the other file.") still inherits the
intent of the conversation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class IntentMatch:
    """Details about the first keyword match used for intent detection."""

    intent: str
    keyword: str = ""


class Intent:
    """Intent enumeration and detection.

    Attributes:
        EXPLAIN: User wants to understand code or architecture.
        IMPLEMENT: User wants to add new functionality.
        REFACTOR: User wants to restructure existing code.
        DEBUG: User wants to find or fix bugs.
        TEST: User wants to write or run tests.
        SEARCH: User wants to find specific information.
        DEFAULT: Fallback for unrecognized requests.
    """

    EXPLAIN = "EXPLAIN"
    IMPLEMENT = "IMPLEMENT"
    REFACTOR = "REFACTOR"
    DEBUG = "DEBUG"
    TEST = "TEST"
    SEARCH = "SEARCH"
    DEFAULT = "DEFAULT"

    _ALL = frozenset([EXPLAIN, IMPLEMENT, REFACTOR, DEBUG, TEST, SEARCH, DEFAULT])

    # Keyword patterns for each intent.
    # Each tuple is (intent, list_of_keywords).
    # Keywords are checked as whole-word set membership (case-insensitive).
    # A keyword matches only when it appears as a complete word, not as
    # a substring of another word (e.g., "work" matches "work" but not
    # "framework" or "workspace").
    # Priority order: EXPLAIN -> REFACTOR -> DEBUG -> TEST -> SEARCH -> IMPLEMENT.
    # Explicit task markers below can override this order for prompts that
    # contain validation requirements such as "add tests", and the action
    # markers in _ACTION_MARKERS override it when a prompt asks for work to
    # be done before it asks for an explanation.
    _KEYWORD_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            EXPLAIN,
            (
                "explain",
                "how does",
                "how do",
                "what is",
                "what does",
                "describe",
                "understand",
                "architecture",
                "overview",
            ),
        ),
        (
            REFACTOR,
            (
                "refactor",
                "restructure",
                "reorganize",
                "rename",
                "cleanup",
                "clean up",
                "simplify",
                "redesign",
                "improve",
            ),
        ),
        (
            DEBUG,
            (
                "debug",
                "fix",
                "bug",
                "error",
                "crash",
                "fail",
                "failing",
                "broken",
                "issue",
                "problem",
                "traceback",
                "exception",
                "throw",
                "fault",
                "diagnose",
            ),
        ),
        (
            TEST,
            (
                "test",
                "unit test",
                "integration test",
                "e2e",
                "coverage",
                "assert",
                "verify",
                "spec",
                "specification",
                "suite",
                "mock",
                "stub",
                "fixture",
            ),
        ),
        (
            SEARCH,
            (
                "find",
                "search",
                "locate",
                "where is",
                "where are",
                "investigate",
                "inspect",
                "check",
                "look into",
                "list",
                "show me",
                "search for",
            ),
        ),
        (
            IMPLEMENT,
            (
                "implement",
                "add",
                "create",
                "build",
                "write",
                "develop",
                "feature",
                "functionality",
                "new",
            ),
        ),
    )

    # Action markers used by the EXPLAIN collision rule, as
    # (whole-word pattern, intent, reported keyword). Deliberately small: only
    # verbs that state work the requester wants done, not nouns that describe
    # it. The earliest marker that precedes the explanation request decides the
    # intent; table order breaks an exact tie.
    _ACTION_MARKERS: tuple[tuple[str, str, str], ...] = (
        (r"\bimplement\b", IMPLEMENT, "implement"),
        (r"\bmodify\b", IMPLEMENT, "modify"),
        (r"\badd\b", IMPLEMENT, "add"),
        (r"\bcreate\b", IMPLEMENT, "create"),
        (r"\brefactor\b", REFACTOR, "refactor"),
        (r"\bfix\b", DEBUG, "fix"),
    )

    # A sentence terminator, used to find the sentence an action verb sits in. A
    # mark counts only when whitespace or the end of the text follows it, so the dot
    # in a file name ("registry.py", "main.py") does not end the sentence early and
    # hide the "?" that closes it. An abbreviation followed by a space ("e.g. a")
    # still reads as a sentence end; telling those apart would need a word list.
    _SENTENCE_END_RE: re.Pattern[str] = re.compile(r"[.?!](?=\s|$)")

    # The openings that make a question sentence a request. Such a sentence
    # addresses the reader and asks them to do the work, so its verb counts even
    # though it ends in "?": "can you add a retry field and explain it?" is a task.
    # Any other sentence ending in "?" is the requester wondering - "where do we add
    # providers?", "what should I fix first?", "does the gateway create one?" - and
    # its verbs do not resolve an explanation collision.
    _QUESTION_OPENERS: tuple[str, ...] = (
        "can you",
        "could you",
        "would you",
        "will you",
        "please",
    )

    # A mutation instruction sequenced after an explanation request: "explain
    # the failure, then fix the parser". Deliberately narrow - a sequencing word
    # immediately followed by an action verb, at most one polite adverb between
    # them - which is what keeps a question out of it ("How do I add a
    # provider?", "Explain it, then how do I add a provider?", "Explain what the
    # code does next."). It reads the verb, not its object: "then add nothing"
    # counts, which is the cost of keeping the pattern bounded. A verb written as a
    # label - "Next fix: none needed." - orders nothing, and the lookahead below
    # rejects exactly that: a colon directly after the sequenced verb.
    _SEQUENCED_ACTION_RE = (
        r"\b(?:then|next|after\s+that|afterwards)\s+(?:please\s+|you\s+can\s+|also\s+)?"
        r"(implement|modify|add|create|refactor|fix)\b(?!:)"
    )

    # The verbs above, mapped to (intent, reported keyword).
    _SEQUENCED_INTENTS: dict[str, tuple[str, str]] = {
        "implement": (IMPLEMENT, "implement"),
        "modify": (IMPLEMENT, "modify"),
        "add": (IMPLEMENT, "add"),
        "create": (IMPLEMENT, "create"),
        "refactor": (REFACTOR, "refactor"),
        "fix": (DEBUG, "fix"),
    }

    @classmethod
    def _extract_words(cls, text: str) -> set[str]:
        """Extract unique lowercase words from text using word boundaries.

        Only matches alphanumeric words (including underscores for
        technical identifiers). Multi-word keywords are checked as
        literal substrings after word extraction.

        Args:
            text: The input text to tokenize.

        Returns:
            A set of unique lowercase words.
        """
        # Extract all word tokens (alphanumeric + underscores).
        return {w.lower() for w in re.findall(r"\b[\w]+\b", text)}

    @staticmethod
    def _remove_negated_commands(text: str) -> str:
        """Remove common negative command phrases before keyword matching."""
        return re.sub(
            r"\b(?:do\s+not|don't|dont|never)\s+\w+\b",
            " ",
            text,
        )

    @classmethod
    def _match_custom_rules(
        cls,
        combined: str,
        words: set[str],
        custom_rules: Mapping[str, Sequence[str]] | None,
    ) -> IntentMatch | None:
        """Return the first configured intent-rule match, if any."""
        if not custom_rules:
            return None

        for raw_intent, patterns in custom_rules.items():
            if not isinstance(raw_intent, str):
                continue

            intent = raw_intent.strip().upper()
            if intent not in cls._ALL:
                continue

            if isinstance(patterns, str) or not isinstance(patterns, Sequence):
                continue

            for raw_pattern in patterns:
                if not isinstance(raw_pattern, str):
                    continue

                pattern = raw_pattern.strip().lower()
                if not pattern:
                    continue

                if " " in pattern:
                    if pattern in combined:
                        return IntentMatch(intent, f"custom:{pattern}")
                elif pattern in words:
                    return IntentMatch(intent, f"custom:{pattern}")

        return None

    @classmethod
    def _keywords_for(cls, intent: str) -> tuple[str, ...]:
        """Return the keyword tuple the priority table registers for an intent."""
        for table_intent, keywords in cls._KEYWORD_PATTERNS:
            if table_intent == intent:
                return keywords
        return ()

    @classmethod
    def _first_keyword_position(cls, keywords: Sequence[str], text: str) -> int | None:
        """Return the offset of the earliest keyword occurrence in ``text``.

        Uses the same matching semantics as the keyword loop - whole-word for
        single-word keywords, literal substring for multi-word ones - so an
        offset is reported exactly when that intent would have matched.

        Args:
            keywords: Keywords of one intent group, already lowercase.
            text: The normalized lowercase message text.

        Returns:
            The character offset of the first match, or ``None`` if the group
            does not match at all.
        """
        earliest: int | None = None
        for keyword in keywords:
            if " " in keyword:
                found = text.find(keyword)
            else:
                match = re.search(rf"\b{re.escape(keyword)}\b", text)
                found = match.start() if match else -1
            if found >= 0 and (earliest is None or found < earliest):
                earliest = found
        return earliest

    @classmethod
    def _match_action_before_explanation(cls, combined: str) -> IntentMatch | None:
        """Resolve an EXPLAIN/action collision in favour of the work.

        Two shapes, in order. An action marker that comes before the explanation
        request ("add a retry field and explain it", "fix it and explain why") is
        the task, and the explanation is the follow-on. Otherwise a mutation
        instruction sequenced after the request ("explain the failure, then fix
        the parser") is still work to be done, so its intent wins.

        A prompt that opens with the explanation and carries no such sequenced
        instruction ("explain how retry is implemented", "how do I add a field")
        stays EXPLAIN, and so does any prompt with no action verb at all.  A verb
        that sits inside a question the prompt is asking rather than an instruction
        it is giving is the third case, and :meth:`_states_work_at` is how that is
        told apart.

        Args:
            combined: Normalized, negation-stripped message text.

        Returns:
            The action intent when one of the two shapes holds, otherwise
            ``None``. ``None`` is also returned when no EXPLAIN keyword is
            present, so the rule can only ever change a prompt that the priority
            table would have called EXPLAIN.
        """
        explanation_at = cls._first_keyword_position(cls._keywords_for(cls.EXPLAIN), combined)
        if explanation_at is None:
            return None

        best: tuple[int, int, str, str] | None = None
        for order, (pattern, intent, keyword) in enumerate(cls._ACTION_MARKERS):
            for match in re.finditer(pattern, combined):
                if match.start() >= explanation_at:
                    break
                if not cls._states_work_at(combined, match.start()):
                    continue
                if best is None or (match.start(), order) < (best[0], best[1]):
                    best = (match.start(), order, intent, keyword)
                break

        if best is not None:
            return IntentMatch(best[2], best[3])

        return cls._match_sequenced_action(combined, explanation_at)

    @classmethod
    def _states_work_at(cls, combined: str, start: int) -> bool:
        """Return True when the verb at ``start`` instructs rather than wonders.

        The sentence that holds the verb runs from the previous terminator to the
        next one.  A sentence ending in ``?`` is the requester asking, not the
        requester telling, so its verb does not resolve an explanation collision -
        unless that sentence opens by addressing the reader, which makes the
        question a request and its verb an instruction again.

        Args:
            combined: Normalized, negation-stripped message text.
            start: Offset of the action verb inside ``combined``.

        Returns:
            ``False`` only when the verb sits in a sentence that ends in ``?`` and
            opens with none of :attr:`_QUESTION_OPENERS`. Text with no terminator
            after the verb is treated as an instruction, so every statement this
            rule already decided is decided exactly as before.
        """
        following = cls._SENTENCE_END_RE.search(combined, start)
        if following is None:
            return True
        end = following.start()
        if combined[end] != "?":
            return True
        begin = 0
        for previous in cls._SENTENCE_END_RE.finditer(combined, 0, start):
            begin = previous.end()
        return combined[begin:end].lstrip().startswith(cls._QUESTION_OPENERS)

    @classmethod
    def _match_sequenced_action(cls, combined: str, explanation_at: int) -> IntentMatch | None:
        """Return the intent of a mutation instruction sequenced after a question.

        "Explain the failure, then fix the parser" asks for two things and the
        second one changes the repository, so the mutation intent wins even
        though the explanation comes first. Only a sequencing word directly
        followed by an action verb qualifies, which is what leaves questions
        ("How do I add a provider?", "explain it, then how do I add one") on
        EXPLAIN. A verb written as a label - "Next fix: none needed." - names a
        slot rather than ordering work, and the pattern rejects a colon written
        directly after the verb.

        Args:
            combined: Normalized, negation-stripped message text.
            explanation_at: Offset of the first EXPLAIN keyword in ``combined``.

        Returns:
            The sequenced intent, or ``None`` when nothing sequenced follows the
            explanation request.
        """
        for match in re.finditer(cls._SEQUENCED_ACTION_RE, combined):
            if match.start() <= explanation_at:
                continue
            intent, keyword = cls._SEQUENCED_INTENTS[match.group(1)]
            return IntentMatch(intent, keyword)

        return None

    @classmethod
    def detect_match(
        cls,
        messages: list[str],
        custom_rules: Mapping[str, Sequence[str]] | None = None,
    ) -> IntentMatch:
        """Detect intent from user messages and return match details.

        The newest non-empty user message is classified on its own first. Only
        when it matches nothing (DEFAULT) does detection fall back to the
        combined text of all user messages, so a keyword in an older turn cannot
        override a newer request that is classifiable by itself, while a
        follow-up carrying no signal of its own ("same for the other file")
        still inherits the intent of the conversation.

        Each classification pass checks custom rules, then the explicit task
        markers, then the action-versus-explanation collision rule, then the
        keyword priority order. First match wins. Keywords are matched as whole
        words, not substrings. If nothing matches, returns DEFAULT.

        Args:
            messages: List of user message strings, oldest first.
            custom_rules: Optional user-configured intent-to-phrases map.

        Returns:
            An IntentMatch with the detected intent and matched keyword.
        """
        texts = [msg.strip().lower() for msg in messages if msg and msg.strip()]

        if not texts:
            return IntentMatch(cls.DEFAULT)

        if len(texts) == 1:
            return cls._classify(texts[0], custom_rules)

        newest = cls._classify(texts[-1], custom_rules)
        if newest.intent != cls.DEFAULT:
            return newest

        return cls._classify(" ".join(texts), custom_rules)

    @classmethod
    def _classify(
        cls,
        combined: str,
        custom_rules: Mapping[str, Sequence[str]] | None,
    ) -> IntentMatch:
        """Classify one normalized message string.

        Args:
            combined: Lowercase message text, already joined when several
                messages are classified together.
            custom_rules: Optional user-configured intent-to-phrases map.

        Returns:
            The IntentMatch for this text, DEFAULT when no rule fires.
        """
        if not combined:
            return IntentMatch(cls.DEFAULT)

        combined = cls._remove_negated_commands(combined)

        # Extract unique words for whole-word matching.
        words = cls._extract_words(combined)

        custom_match = cls._match_custom_rules(combined, words, custom_rules)
        if custom_match is not None:
            return custom_match

        explicit_refactor = re.search(
            r"\brefactor(?:ing)?\s+(?:investigation|plan|recommendation|analysis)\b",
            combined,
        )
        if explicit_refactor:
            return IntentMatch(cls.REFACTOR, "refactor")

        explicit_implementation = re.search(
            r"\bimplementation\s+task\b|\bmodify\s+files\b",
            combined,
        )
        if explicit_implementation:
            return IntentMatch(cls.IMPLEMENT, "implement")

        action_match = cls._match_action_before_explanation(combined)
        if action_match is not None:
            return action_match

        for intent, keywords in cls._KEYWORD_PATTERNS:
            for keyword in keywords:
                # Multi-word keywords: check as literal substring.
                if " " in keyword:
                    if keyword in combined:
                        return IntentMatch(intent, keyword)
                # Single-word keywords: check as set membership.
                elif keyword in words:
                    return IntentMatch(intent, keyword)

        return IntentMatch(cls.DEFAULT)

    @classmethod
    def detect(
        cls,
        messages: list[str],
        custom_rules: Mapping[str, Sequence[str]] | None = None,
    ) -> str:
        """Detect intent from user messages.

        Checks custom rules, the explicit task markers and the action
        versus explanation rule, then the keywords in priority order.
        First match wins. Keywords are matched as whole words, not
        substrings. If no keywords match, returns DEFAULT. User-configured
        custom rules are checked before built-in rules.

        Args:
            messages: List of user message strings.
            custom_rules: Optional user-configured intent-to-phrases map.

        Returns:
            The detected intent string.
        """
        return cls.detect_match(messages, custom_rules=custom_rules).intent
