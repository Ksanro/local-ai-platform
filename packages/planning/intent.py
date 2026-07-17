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
"""

from __future__ import annotations

import re


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
    # Priority order: EXPLAIN -> REFACTOR -> DEBUG -> TEST -> SEARCH -> IMPLEMENT
    # REFACTOR and TEST come before IMPLEMENT to avoid false positives
    # where words like "build" or "write" appear in symbol names.
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
                "work",
                "flow",
                "mechanism",
                "purpose",
                "role",
                "function",
                "means",
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
                "resolve",
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

    @classmethod
    def detect(cls, messages: list[str]) -> str:
        """Detect intent from user messages.

        Checks keywords in priority order. First match wins.
        Keywords are matched as whole words, not substrings.
        If no keywords match, returns DEFAULT.

        Args:
            messages: List of user message strings.

        Returns:
            The detected intent string.
        """
        if not messages:
            return cls.DEFAULT

        # Combine all messages into a single lowercase string for matching.
        combined = " ".join(msg.strip().lower() for msg in messages if msg and msg.strip())

        if not combined:
            return cls.DEFAULT

        # Extract unique words for whole-word matching.
        words = cls._extract_words(combined)

        for intent, keywords in cls._KEYWORD_PATTERNS:
            for keyword in keywords:
                # Multi-word keywords: check as literal substring.
                if " " in keyword:
                    if keyword in combined:
                        return intent
                # Single-word keywords: check as set membership.
                elif keyword in words:
                    return intent

        return cls.DEFAULT