import httpx
import pytest
import respx
from pydantic import SecretStr

from app.config import Settings
from scripts.list_models import (
    ProviderModels,
    collect_models,
    fetch_gemini_models,
    fetch_openai_compatible_models,
    render,
)

GEMINI_URL = "https://gemini.test/v1beta"
HF_URL = "https://hf.test/v1"
NVIDIA_URL = "https://nvidia.test/v1"
LOCAL_URL = "http://localhost:11434/v1"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        gemini_base_url=GEMINI_URL,
        hf_base_url=HF_URL,
        nvidia_base_url=NVIDIA_URL,
        local_base_url=LOCAL_URL,
    )


async def test_gemini_keeps_only_generative_models_and_sends_key_in_header(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(f"{GEMINI_URL}/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/text-embedding",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        models = await fetch_gemini_models(client, GEMINI_URL, "secret-key")

    assert models == ["gemini-flash"]
    request = route.calls.last.request
    assert request.headers["x-goog-api-key"] == "secret-key"
    assert "secret-key" not in str(request.url)


async def test_openai_compatible_returns_sorted_ids_with_bearer_auth(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(f"{NVIDIA_URL}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "z-model"}, {"id": "a-model"}]})
    )

    async with httpx.AsyncClient() as client:
        models = await fetch_openai_compatible_models(client, NVIDIA_URL, "nvapi-x")

    assert models == ["a-model", "z-model"]
    assert route.calls.last.request.headers["authorization"] == "Bearer nvapi-x"


async def test_collect_reports_missing_keys_and_failures_without_raising(
    respx_mock: respx.MockRouter, settings: Settings
) -> None:
    settings.hf_token = SecretStr("hf-token")
    settings.nvidia_api_key = SecretStr("nvapi-x")
    respx_mock.get(f"{HF_URL}/models").mock(return_value=httpx.Response(401))
    respx_mock.get(f"{NVIDIA_URL}/models").mock(return_value=httpx.Response(200, text="not json"))
    respx_mock.get(f"{LOCAL_URL}/models").mock(side_effect=httpx.ConnectError("refused"))

    async with httpx.AsyncClient() as client:
        results = await collect_models(settings, client)

    assert results == [
        ProviderModels("gemini", [], "not configured (set GEMINI_API_KEY)"),
        ProviderModels("huggingface", [], "request failed: HTTP 401"),
        ProviderModels("nvidia", [], "unexpected response format"),
        ProviderModels("local", [], f"no server at {LOCAL_URL} (start one or set LOCAL_BASE_URL)"),
    ]


async def test_collect_reports_network_errors(
    respx_mock: respx.MockRouter, settings: Settings
) -> None:
    settings.gemini_api_key = SecretStr("key")
    settings.nvidia_api_key = SecretStr("nvapi-x")
    respx_mock.get(f"{GEMINI_URL}/models").mock(side_effect=httpx.ConnectTimeout("slow"))
    respx_mock.get(f"{NVIDIA_URL}/models").mock(side_effect=httpx.ConnectError("refused"))
    respx_mock.get(f"{LOCAL_URL}/models").mock(return_value=httpx.Response(503))

    async with httpx.AsyncClient() as client:
        results = await collect_models(settings, client)

    assert results[0] == ProviderModels("gemini", [], "request failed: ConnectTimeout")
    assert results[2] == ProviderModels("nvidia", [], "request failed: ConnectError")
    assert results[3] == ProviderModels("local", [], "request failed: HTTP 503")


async def test_local_server_models_are_listed_without_a_key(
    respx_mock: respx.MockRouter, settings: Settings
) -> None:
    route = respx_mock.get(f"{LOCAL_URL}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "qwen3:4b"}]})
    )

    async with httpx.AsyncClient() as client:
        results = await collect_models(settings, client)

    assert results[3] == ProviderModels("local", ["qwen3:4b"])
    assert "authorization" not in route.calls.last.request.headers


def test_render_filters_by_case_insensitive_match() -> None:
    results = [
        ProviderModels("nvidia", ["meta/llama-3.3-70b", "qwen/qwen2.5-coder"]),
        ProviderModels("gemini", [], "not configured (set GEMINI_API_KEY)"),
    ]

    output = render(results, match="LLAMA")

    assert output.splitlines() == [
        "nvidia (1 model)",
        "  meta/llama-3.3-70b",
        "gemini: not configured (set GEMINI_API_KEY)",
    ]
