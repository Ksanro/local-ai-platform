"""Application configuration using Pydantic Settings.

Settings are loaded from environment variables (prefixed with ``APP_``)
and can be overridden via a ``config.yaml`` file.
"""

import json
from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings

_CONTEXT_INTENTS = frozenset(
    ["EXPLAIN", "IMPLEMENT", "REFACTOR", "DEBUG", "TEST", "SEARCH", "DEFAULT"]
)


def parse_intent_budget_map(value: str) -> dict[str, int]:
    """Parse ``INTENT:tokens`` pairs from a comma-separated setting."""
    budgets: dict[str, int] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item or ":" not in item:
            continue
        raw_intent, raw_tokens = item.split(":", 1)
        intent = raw_intent.strip().upper()
        try:
            tokens = int(raw_tokens.strip())
        except ValueError:
            continue
        if intent and tokens > 0:
            budgets[intent] = tokens
    return budgets


def parse_context_intent_rules(value: str) -> dict[str, tuple[str, ...]]:
    """Parse user-configured intent rules from a JSON object setting.

    Expected shape:
    ``{"IMPLEMENT": ["adauga", "modifica"], "SEARCH": ["cauta"]}``

    Invalid JSON, unknown intents, non-string patterns, and empty patterns
    are ignored so a bad local setting cannot break request handling.
    """
    if not value.strip():
        return {}

    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    rules: dict[str, tuple[str, ...]] = {}
    for raw_intent, raw_patterns in parsed.items():
        if not isinstance(raw_intent, str):
            continue

        intent = raw_intent.strip().upper()
        if intent not in _CONTEXT_INTENTS:
            continue

        if isinstance(raw_patterns, str):
            patterns = [raw_patterns]
        elif isinstance(raw_patterns, list):
            patterns = raw_patterns
        else:
            continue

        cleaned = tuple(
            pattern.strip()
            for pattern in patterns
            if isinstance(pattern, str) and pattern.strip()
        )
        if cleaned:
            rules[intent] = cleaned

    return rules


class Settings(BaseSettings):
    """Application settings.

    Loaded from environment variables with the ``APP_`` prefix.
    Example: ``APP_LOG_LEVEL=DEBUG`` sets ``log_level`` to ``"DEBUG"``.
    """

    app_name: str = "Local AI Platform"
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]
    default_provider: str = "vllm"
    default_model: str = "default"
    repository_context_enabled: bool = True
    repository_path: str = "."
    repository_exclude_tests: bool = False
    repository_exclude_globs: str = "scripts/**"  # comma-separated glob list; empty disables
    repository_context_max_tokens: int = 4096
    repository_context_intent_budgets: str = ""
    context_intent_rules: str = ""
    models_config: str = ""  # JSON array of model definitions; empty = single-provider fallback
    context_delta_injection: bool = True  # inject only symbols not already sent
    context_delta_cache_size: int = 256  # max conversation keys in LRU cache
    session_log_enabled: bool = True  # on by default — opt in
    session_log_path: str = "logs/sessions.jsonl"
    history_cap_enabled: bool = False  # on by default — opt in to reduce prefill
    history_cap_tokens: int = 0  # APP_HISTORY_CAP_TOKENS; 0 = derive from context_window

    model_config = {"env_prefix": "APP_"}

    @property
    def repository_context_intent_budget_map(self) -> dict[str, int]:
        """Return configured per-intent repository-context budgets."""
        return parse_intent_budget_map(self.repository_context_intent_budgets)

    @property
    def context_intent_rule_map(self) -> dict[str, tuple[str, ...]]:
        """Return configured user intent-detection rules."""
        return parse_context_intent_rules(self.context_intent_rules)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get the application settings instance.

    Uses ``lru_cache`` to ensure a single instance is created and
    reused across calls. This replaces the previous mutable-global
    singleton pattern.

    Returns:
        The application ``Settings`` instance.
    """
    return Settings()
