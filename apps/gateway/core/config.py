"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    app_name: str = "Local AI Platform"
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]

    model_config = {"env_prefix": "APP_"}


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


