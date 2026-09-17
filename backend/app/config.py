"""Application settings, loaded from environment variables and ``backend/.env``.

All configuration flows through :class:`Settings`, so no other module reads
``os.environ`` directly and tests can build settings explicitly.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]
LLMMode = Literal["live", "mock"]


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

    # A provider is enabled when its model id (and, for hosted providers, its key) is set.
    llm_mode: LLMMode = "live"
    providers_config_path: Path = BACKEND_ROOT / "config" / "providers.yaml"

    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    hf_token: SecretStr | None = None
    hf_model_large: str | None = None
    hf_model_small: str | None = None
    hf_base_url: str = "https://router.huggingface.co/v1"
    nvidia_api_key: SecretStr | None = None
    nvidia_model: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    local_model: str | None = None
    local_base_url: str = "http://localhost:11434/v1"

    opengrep_path: str | None = None

    # Scans submitted through the web API.
    storage_dir: Path = BACKEND_ROOT / "storage"
    retention_hours: PositiveInt = 24
    max_concurrent_scans: PositiveInt = 2


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once from the environment."""
    return Settings()
