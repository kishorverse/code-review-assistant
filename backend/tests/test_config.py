import pytest

from app.config import Settings


def test_defaults_have_no_api_keys() -> None:
    settings = Settings(_env_file=None)

    assert settings.gemini_api_key is None
    assert settings.hf_token is None
    assert settings.nvidia_api_key is None
    assert settings.log_level == "INFO"


def test_reads_api_key_from_environment_and_masks_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-value")

    settings = Settings(_env_file=None)

    assert settings.nvidia_api_key is not None
    assert settings.nvidia_api_key.get_secret_value() == "nvapi-test-value"
    assert "nvapi-test-value" not in repr(settings)


def test_empty_api_key_counts_as_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")

    settings = Settings(_env_file=None)

    assert settings.gemini_api_key is None


def test_parses_cors_origins_from_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000", "https://example.com"]')

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]


def test_rejects_unknown_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValueError, match="log_level"):
        Settings(_env_file=None)
