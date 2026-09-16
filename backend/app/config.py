"""Application settings, loaded from environment variables and ``backend/.env``.

All configuration flows through :class:`Settings`, so no other module reads
``os.environ`` directly and tests can build settings explicitly.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]


class Settings(BaseSettings):
    """Typed runtime configuration.

    API keys are ``SecretStr`` so they are masked if a settings object is ever
    logged or printed.
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        # `GEMINI_API_KEY=` in .env means "not configured", not an empty key.
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"
    cors_origins: list[str] = ["http://localhost:5173"]

    gemini_api_key: SecretStr | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    hf_token: SecretStr | None = None
    hf_base_url: str = "https://router.huggingface.co/v1"
    nvidia_api_key: SecretStr | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once from the environment."""
    return Settings()
