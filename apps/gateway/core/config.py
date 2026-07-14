"""Application configuration using Pydantic Settings.

Settings are loaded from environment variables (prefixed with ``APP_``)
and can be overridden via a ``config.yaml`` file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings.

    Loaded from environment variables with the ``APP_`` prefix.
    Example: ``APP_LOG_LEVEL=DEBUG`` sets ``log_level`` to ``"DEBUG"``.
    """

    app_name: str = "Local AI Platform"
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]

    model_config = {"env_prefix": "APP_"}


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

