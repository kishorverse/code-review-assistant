import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from pydantic import SecretStr

from app.errors import (
    ProviderAuthError,
    ProviderRequestError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.llm.models import LLMRequest, Task
from app.llm.providers.base import parse_retry_after
from app.llm.providers.openai_compatible import OpenAICompatibleProvider
from tests.llm.conftest import FakeClock

BASE_URL = "https://nim.test/v1"
URL = f"{BASE_URL}/chat/completions"
REQUEST = LLMRequest(task=Task.REVIEW, system="You review code.", user="1 | x = 1")


def completion(content: str = '{"findings": []}') -> dict[str, object]:
    return {
        "model": "meta/llama-3.3-70b-instruct",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 42, "completion_tokens": 7},
    }


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as http:
        yield http


def provider(
    client: httpx.AsyncClient,
    clock: FakeClock,
    *,
    api_key: str | None = "nvapi-test",
    json_mode: bool = True,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="nvidia",
        model="meta/llama-3.3-70b-instruct",
        base_url=BASE_URL,
        api_key=SecretStr(api_key) if api_key else None,
        external=True,
        client=client,
        clock=clock,
        json_mode=json_mode,
    )


async def test_sends_chat_request_and_parses_content_and_usage(
    respx_mock: respx.MockRouter, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    route = respx_mock.post(URL).mock(return_value=httpx.Response(200, json=completion()))

    response = await provider(client, clock).complete(REQUEST)

    sent = json.loads(route.calls.last.request.content)
    assert sent["messages"] == [
        {"role": "system", "content": "You review code."},
        {"role": "user", "content": "1 | x = 1"},
    ]
    assert sent["response_format"] == {"type": "json_object"}
    assert (sent["temperature"], sent["max_tokens"], sent["stream"]) == (0.1, 2048, False)
    assert route.calls.last.request.headers["authorization"] == "Bearer nvapi-test"
    assert (response.text, response.provider, response.input_tokens, response.output_tokens) == (
        '{"findings": []}',
        "nvidia",
        42,
        7,
    )


async def test_local_provider_sends_no_authorization_and_can_skip_json_mode(
    respx_mock: respx.MockRouter, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    route = respx_mock.post(URL).mock(return_value=httpx.Response(200, json=completion()))

    await provider(client, clock, api_key=None, json_mode=False).complete(REQUEST)

    assert "authorization" not in route.calls.last.request.headers
    assert "response_format" not in json.loads(route.calls.last.request.content)


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(429, headers={"Retry-After": "12"}), RateLimitedError),
        (httpx.Response(402, json={"error": "monthly credits exceeded"}), QuotaExhaustedError),
        (httpx.Response(401, json={"error": {"message": "bad key"}}), ProviderAuthError),
        (httpx.Response(403), ProviderAuthError),
        (httpx.Response(503, text="overloaded"), ProviderUnavailableError),
        (httpx.Response(408), ProviderUnavailableError),
        (httpx.Response(404, json={"error": {"message": "model not found"}}), ProviderRequestError),
        (httpx.Response(200, text="not json"), ProviderRequestError),
        (httpx.Response(200, json={"choices": []}), ProviderRequestError),
        (httpx.Response(200, json=completion(content="   ")), ProviderRequestError),
        (httpx.Response(200, json={"choices": ["unexpected"]}), ProviderRequestError),
        (httpx.Response(200, json=[completion()]), ProviderRequestError),
    ],
)
async def test_maps_failures_to_provider_errors(
    respx_mock: respx.MockRouter,
    client: httpx.AsyncClient,
    clock: FakeClock,
    response: httpx.Response,
    error: type[Exception],
) -> None:
    respx_mock.post(URL).mock(return_value=response)

    with pytest.raises(error):
        await provider(client, clock).complete(REQUEST)


async def test_rate_limit_carries_retry_after_seconds(
    respx_mock: respx.MockRouter, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    respx_mock.post(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "12"}))

    with pytest.raises(RateLimitedError) as caught:
        await provider(client, clock).complete(REQUEST)

    assert caught.value.retry_after == 12.0
    assert caught.value.provider == "nvidia"


async def test_garbled_usage_counts_as_zero(
    respx_mock: respx.MockRouter, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    body = completion() | {"usage": ["not", "a", "dict"]}
    respx_mock.post(URL).mock(return_value=httpx.Response(200, json=body))

    response = await provider(client, clock).complete(REQUEST)

    assert (response.input_tokens, response.output_tokens) == (0, 0)


@pytest.mark.parametrize("failure", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
async def test_network_failures_are_unavailable(
    respx_mock: respx.MockRouter,
    client: httpx.AsyncClient,
    clock: FakeClock,
    failure: Exception,
) -> None:
    respx_mock.post(URL).mock(side_effect=failure)

    with pytest.raises(ProviderUnavailableError):
        await provider(client, clock).complete(REQUEST)


def test_retry_after_accepts_seconds_and_http_dates(clock: FakeClock) -> None:
    http_date = "Thu, 17 Sep 2026 08:00:30 GMT"

    assert parse_retry_after("7", clock.now()) == 7.0
    assert parse_retry_after(http_date, clock.now()) == 30.0
    assert parse_retry_after("soon", clock.now()) is None
    assert parse_retry_after(None, clock.now()) is None
