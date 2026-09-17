import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

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
from app.llm.providers.gemini import GeminiProvider, next_quota_reset, parse_duration
from tests.llm.conftest import FakeClock

BASE_URL = "https://gemini.test/v1beta"
MODEL = "gemini-flash-test"
URL = f"{BASE_URL}/models/{MODEL}:generateContent"
REQUEST = LLMRequest(task=Task.VERIFY, system="Be skeptical.", user="Is this real?")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as http:
        yield http


def gemini(client: httpx.AsyncClient, clock: FakeClock) -> GeminiProvider:
    return GeminiProvider(
        model=MODEL, base_url=BASE_URL, api_key=SecretStr("g-key"), client=client, clock=clock
    )


def quota_error(*details: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "message": "You exceeded your current quota.",
                "status": "RESOURCE_EXHAUSTED",
                "details": list(details),
            }
        },
    )


async def test_sends_system_instruction_json_mode_and_key_in_header(
    respx_mock: respx.MockRouter, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    route = respx_mock.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "internal reasoning", "thought": True},
                                {"text": '{"verdict": "valid"}'},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 30,
                    "candidatesTokenCount": 5,
                    "thoughtsTokenCount": 3,
                },
            },
        )
    )

    response = await gemini(client, clock).complete(REQUEST)

    request = route.calls.last.request
    body = json.loads(request.content)
    assert request.headers["x-goog-api-key"] == "g-key"
    assert "g-key" not in str(request.url)
    assert body["systemInstruction"] == {"parts": [{"text": "Be skeptical."}]}
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert response.text == '{"verdict": "valid"}'
    assert (response.input_tokens, response.output_tokens) == (30, 8)


async def test_short_term_rate_limit_uses_the_suggested_retry_delay(
    respx_mock: respx.MockRouter, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    respx_mock.post(URL).mock(
        return_value=quota_error(
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "34s"},
        )
    )

    with pytest.raises(RateLimitedError) as caught:
        await gemini(client, clock).complete(REQUEST)

    assert caught.value.retry_after == 34.0


async def test_daily_quota_is_exhausted_until_midnight_pacific(
    respx_mock: respx.MockRouter, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    respx_mock.post(URL).mock(
        return_value=quota_error(
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "10s"},
        )
    )

    with pytest.raises(QuotaExhaustedError) as caught:
        await gemini(client, clock).complete(REQUEST)

    assert caught.value.resets_at == datetime(2026, 9, 18, 7, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(403, json={"error": {"message": "API key not valid"}}), ProviderAuthError),
        (httpx.Response(500), ProviderUnavailableError),
        (httpx.Response(400, json={"error": {"message": "bad request"}}), ProviderRequestError),
        (
            httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
            ProviderRequestError,
        ),
        (
            httpx.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS"}]}),
            ProviderRequestError,
        ),
        (httpx.Response(200, json={"candidates": ["unexpected"]}), ProviderRequestError),
        (
            httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": 7}]}}]}),
            ProviderRequestError,
        ),
        (httpx.Response(429, text="Too Many Requests"), RateLimitedError),
        (
            httpx.Response(429, json={"error": {"details": ["x", {"violations": "x"}]}}),
            RateLimitedError,
        ),
    ],
)
async def test_maps_other_failures(
    respx_mock: respx.MockRouter,
    client: httpx.AsyncClient,
    clock: FakeClock,
    response: httpx.Response,
    error: type[Exception],
) -> None:
    respx_mock.post(URL).mock(return_value=response)

    with pytest.raises(error):
        await gemini(client, clock).complete(REQUEST)


async def test_missing_or_garbled_usage_counts_as_zero(
    respx_mock: respx.MockRouter, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    respx_mock.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "{}"}]}}],
                "usageMetadata": {"promptTokenCount": "many"},
            },
        )
    )

    response = await gemini(client, clock).complete(REQUEST)

    assert (response.input_tokens, response.output_tokens) == (0, 0)


def test_quota_reset_follows_pacific_daylight_saving() -> None:
    summer = next_quota_reset(datetime(2026, 7, 1, 12, 0, tzinfo=UTC))
    winter = next_quota_reset(datetime(2026, 12, 1, 12, 0, tzinfo=UTC))

    assert summer == datetime(2026, 7, 2, 7, 0, tzinfo=UTC)
    assert winter == datetime(2026, 12, 2, 8, 0, tzinfo=UTC)


def test_parse_duration() -> None:
    assert parse_duration("1.5s") == 1.5
    assert parse_duration("34s") == 34.0
    assert parse_duration("soon") is None
    assert parse_duration(None) is None
