from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from app.config import Settings
from app.errors import ConfigError
from app.llm.config import load_providers_config
from app.llm.factory import build_routed_providers, build_router, is_loopback_url
from app.llm.models import CallRecord, CallStatus, LLMRequest, Task
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.mock import MockProvider
from app.llm.providers.openai_compatible import OpenAICompatibleProvider
from tests.llm.conftest import FakeClock

PLACEHOLDER_CREDENTIAL = "placeholder"

ALL_KEYS = {
    "gemini_api_key": PLACEHOLDER_CREDENTIAL,
    "gemini_model": "gemini-flash",
    "hf_token": PLACEHOLDER_CREDENTIAL,
    "hf_model_large": "meta-llama/large",
    "hf_model_small": "meta-llama/small",
    "nvidia_api_key": PLACEHOLDER_CREDENTIAL,
    "nvidia_model": "meta/llama",
    "local_model": "qwen3:4b",
}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as http:
        yield http


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)


async def test_no_keys_or_models_means_no_providers(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    router = build_router(settings(), client, clock)

    assert router.status() == []


async def test_builds_each_provider_whose_model_and_key_are_set(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    config = load_providers_config(settings().providers_config_path)

    routed = build_routed_providers(settings(**ALL_KEYS), config, client, clock)

    by_name = {entry.provider.name: entry for entry in routed}
    assert set(by_name) == {"gemini", "nvidia", "hf-large", "hf-small", "local"}
    assert isinstance(by_name["gemini"].provider, GeminiProvider)
    assert all(
        isinstance(by_name[name].provider, OpenAICompatibleProvider)
        for name in ("nvidia", "hf-large", "hf-small", "local")
    )
    assert [name for name, entry in by_name.items() if not entry.provider.external] == ["local"]
    assert by_name["hf-large"].limiter is by_name["hf-small"].limiter
    assert by_name["nvidia"].limiter is not by_name["gemini"].limiter
    assert by_name["local"].timeout_seconds == config.providers["local"].timeout_seconds


@pytest.mark.parametrize(
    ("missing", "absent"),
    [
        ("gemini_model", "gemini"),
        ("gemini_api_key", "gemini"),
        ("hf_token", "hf-large"),
        ("hf_model_small", "hf-small"),
        ("nvidia_api_key", "nvidia"),
        ("local_model", "local"),
    ],
)
async def test_a_provider_missing_its_key_or_model_is_left_out(
    client: httpx.AsyncClient, clock: FakeClock, missing: str, absent: str
) -> None:
    values = {key: value for key, value in ALL_KEYS.items() if key != missing}

    names = {status.name for status in build_router(settings(**values), client, clock).status()}

    assert absent not in names
    assert len(names) == (3 if missing == "hf_token" else 4)


async def test_local_server_on_another_host_needs_consent(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    remote = settings(local_model="qwen3:4b", local_base_url="http://gpu-box.lan:11434/v1")

    [local] = build_router(remote, client, clock).status()

    assert local.external


@pytest.mark.parametrize(
    ("url", "loopback"),
    [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:1234/v1", True),
        ("http://[::1]:8080/v1", True),
        ("http://192.168.1.20:11434/v1", False),
        ("https://localhost.example.com/v1", False),
        ("not a url", False),
    ],
)
def test_is_loopback_url(url: str, loopback: bool) -> None:
    assert is_loopback_url(url) is loopback


async def test_mock_mode_serves_every_route_offline_without_rate_limits(
    client: httpx.AsyncClient, clock: FakeClock, respx_mock: respx.MockRouter
) -> None:
    router = build_router(settings(llm_mode="mock"), client, clock)
    records: list[CallRecord] = []

    for index in range(30):
        await router.complete(
            LLMRequest(task=Task.VERIFY, system="s", user=str(index), allow_external=True),
            on_call=records.append,
        )
    private = await router.complete(LLMRequest(task=Task.REVIEW, system="s", user="u"))

    assert {status.name for status in router.status()} == {
        "gemini",
        "nvidia",
        "hf-large",
        "hf-small",
        "local",
    }
    assert {record.status for record in records} == {CallStatus.OK}
    assert clock.sleeps == []
    assert private.provider == "local"
    assert private.model == "mock-local"
    assert not respx_mock.calls


async def test_mock_providers_are_mocks(client: httpx.AsyncClient, clock: FakeClock) -> None:
    mock_settings = settings(llm_mode="mock")
    config = load_providers_config(mock_settings.providers_config_path)

    routed = build_routed_providers(mock_settings, config, client, clock)

    assert all(isinstance(entry.provider, MockProvider) for entry in routed)


async def test_missing_config_file_is_a_config_error(
    client: httpx.AsyncClient, clock: FakeClock, tmp_path: Path
) -> None:
    broken = settings(providers_config_path=tmp_path / "absent.yaml")

    with pytest.raises(ConfigError):
        build_router(broken, client, clock)
