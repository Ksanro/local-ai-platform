"""Tests for gateway configuration helpers."""

from __future__ import annotations

import pytest

from apps.gateway.core.config import (
    Settings,
    parse_context_intent_rules,
    parse_intent_budget_map,
)


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


def test_parse_context_intent_rules() -> None:
    """Valid user intent rules are parsed and normalized."""
    value = (
        '{"implement": ["adauga", "modifica"], '
        '"SEARCH": "cauta", "NOPE": ["ignored"], "DEBUG": ["", 3]}'
    )

    assert parse_context_intent_rules(value) == {
        "IMPLEMENT": ("adauga", "modifica"),
        "SEARCH": ("cauta",),
    }


def test_parse_context_intent_rules_ignores_invalid_json() -> None:
    """Invalid user intent rules fall back to no custom rules."""
    assert parse_context_intent_rules("not json") == {}


def test_settings_exposes_context_intent_rule_map() -> None:
    """Settings exposes parsed user intent-detection rules."""
    settings = Settings(context_intent_rules='{"debug": ["eroare"]}')

    assert settings.context_intent_rule_map == {"DEBUG": ("eroare",)}


def test_settings_include_tests_by_default() -> None:
    """Repository indexing should include tests unless explicitly disabled."""
    settings = Settings()

    assert settings.repository_exclude_tests is False


def test_changed_file_signal_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Change-aware ranking stays dormant unless it is explicitly enabled."""
    monkeypatch.delenv("APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED", raising=False)
    monkeypatch.delenv("APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS", raising=False)

    settings = Settings()

    assert settings.repository_context_changed_files_enabled is False
    assert settings.repository_context_changed_files_ttl_seconds == 0


def test_changed_file_signal_reads_app_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both knobs are configured through ``APP_`` environment variables."""
    monkeypatch.setenv("APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED", "true")
    monkeypatch.setenv("APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS", "45")

    settings = Settings()

    assert settings.repository_context_changed_files_enabled is True
    assert settings.repository_context_changed_files_ttl_seconds == 45
