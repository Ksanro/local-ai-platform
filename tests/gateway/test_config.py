"""Tests for gateway configuration helpers."""

from __future__ import annotations

from apps.gateway.core.config import Settings, parse_intent_budget_map


def test_parse_intent_budget_map() -> None:
    """Valid intent budget entries are parsed and normalized."""
    value = "search:2048, DEBUG:4096, invalid, TEST:nope, explain:8192, zero:0"

    assert parse_intent_budget_map(value) == {
        "SEARCH": 2048,
        "DEBUG": 4096,
        "EXPLAIN": 8192,
    }


def test_settings_exposes_intent_budget_map() -> None:
    """Settings exposes parsed per-intent repository-context budgets."""
    settings = Settings(
        repository_context_intent_budgets="search:2048,debug:4096"
    )

    assert settings.repository_context_intent_budget_map == {
        "SEARCH": 2048,
        "DEBUG": 4096,
    }
