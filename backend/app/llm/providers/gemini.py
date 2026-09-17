"""Google Gemini over the Generative Language REST API.

Gemini reports two different 429s: a short-term rate limit with a suggested
retry delay, and an exhausted daily quota that only resets at midnight Pacific
time. Telling them apart lets the router wait seconds for the first and skip
Gemini for the rest of the day for the second.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import SecretStr

from app.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRequestError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.llm.clock import Clock
from app.llm.models import LLMRequest, LLMResponse
from app.llm.providers.base import (
    error_detail,
    json_object,
    post_json,
    raise_for_status,
    usage_count,
)

NAME = "gemini"
QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")
_DURATION = re.compile(r"^(?P<seconds>\d+(?:\.\d+)?)s$")


class GeminiProvider:
    """Calls ``models/{model}:generateContent``."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: SecretStr,
        client: httpx.AsyncClient,
        clock: Clock,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._model = model
        self._url = f"{base_url.rstrip('/')}/models/{model}:generateContent"
        self._api_key = api_key
        self._client = client
        self._clock = clock
        self._timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        """See :class:`~app.llm.providers.base.LLMProvider`."""
        return NAME

    @property
    def model(self) -> str:
        """See :class:`~app.llm.providers.base.LLMProvider`."""
        return self._model

    @property
    def external(self) -> bool:
        """Gemini is a hosted service."""
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send one generateContent request."""
        generation: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_output_tokens,
        }
        if request.json_output:
            generation["responseMimeType"] = "application/json"
        body = {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": [{"text": request.user}]}],
            "generationConfig": generation,
        }
        # The key travels in a header, never in the URL, so it cannot end up in logs.
        headers = {"x-goog-api-key": self._api_key.get_secret_value()}

        response, latency_ms = await post_json(
            self._client,
            NAME,
            self._url,
            headers=headers,
            body=body,
            timeout_seconds=self._timeout_seconds,
        )
        now = self._clock.now()
        if response.status_code == 429:
            raise rate_limit_error(response, now)
        if response.status_code == 400 and has_error_reason(response, "API_KEY_INVALID"):
            # Gemini reports an invalid or expired key as a 400, not a 401.
            raise ProviderAuthError(NAME, f"API key rejected: {error_detail(response)}")
        raise_for_status(NAME, response, now)
        return self._parse(json_object(NAME, response), latency_ms)

    def _parse(self, payload: dict[str, Any], latency_ms: int) -> LLMResponse:
        try:
            text = response_text(payload)
        except (AttributeError, IndexError, KeyError, TypeError) as error:
            raise ProviderUnavailableError(NAME, "response had an unexpected shape") from error
        usage = payload.get("usageMetadata")
        return LLMResponse(
            text=text,
            provider=NAME,
            model=str(payload.get("modelVersion") or self._model),
            input_tokens=usage_count(usage, "promptTokenCount"),
            # Thinking tokens are billed and rate limited as output.
            output_tokens=usage_count(usage, "candidatesTokenCount")
            + usage_count(usage, "thoughtsTokenCount"),
            latency_ms=latency_ms,
        )


def response_text(payload: dict[str, Any]) -> str:
    """The first candidate's answer, leaving out thought summaries.

    Raises:
        ProviderRequestError: If the prompt was blocked, or the answer is empty or
            was cut off at the output token limit.
    """
    candidates = payload.get("candidates") or []
    if not candidates:
        reason = (payload.get("promptFeedback") or {}).get("blockReason", "unknown")
        raise ProviderRequestError(NAME, f"no candidates returned (block reason: {reason})")
    candidate = candidates[0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        # Thinking tokens count towards the limit, so this can happen with little visible text.
        raise ProviderRequestError(NAME, "response was cut off at the output token limit")
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    if not text.strip():
        finish = candidate.get("finishReason", "unknown")
        raise ProviderRequestError(NAME, f"response had no text (finish reason: {finish})")
    return text


def rate_limit_error(response: httpx.Response, now: datetime) -> ProviderError:
    """Distinguish an exhausted daily quota from a short-term rate limit."""
    retry_after = None
    for detail in error_details(response):
        kind = str(detail.get("@type", ""))
        if kind.endswith("QuotaFailure") and is_daily_quota(detail):
            return QuotaExhaustedError(NAME, "daily quota used", resets_at=next_quota_reset(now))
        if kind.endswith("RetryInfo"):
            retry_after = parse_duration(detail.get("retryDelay"))
    return RateLimitedError(NAME, f"rate limited: {error_detail(response)}", retry_after)


def error_details(response: httpx.Response) -> list[dict[str, Any]]:
    """The ``google.rpc`` detail objects of an error body, if it has any."""
    try:
        details = response.json()["error"]["details"]
    except (ValueError, KeyError, TypeError):
        return []
    return (
        [detail for detail in details if isinstance(detail, dict)]
        if isinstance(details, list)
        else []
    )


def has_error_reason(response: httpx.Response, reason: str) -> bool:
    """Whether an error body carries a ``google.rpc.ErrorInfo`` with this reason."""
    return any(
        str(detail.get("@type", "")).endswith("ErrorInfo") and detail.get("reason") == reason
        for detail in error_details(response)
    )


def is_daily_quota(quota_failure: dict[str, Any]) -> bool:
    """Whether a ``QuotaFailure`` names a per-day quota."""
    violations = quota_failure.get("violations")
    return isinstance(violations, list) and any(
        isinstance(violation, dict) and "PerDay" in str(violation.get("quotaId", ""))
        for violation in violations
    )


def next_quota_reset(now: datetime) -> datetime:
    """Gemini's daily quotas reset at midnight Pacific time."""
    local = now.astimezone(QUOTA_TIMEZONE)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(UTC)


def parse_duration(value: object) -> float | None:
    """Parse a protobuf duration such as ``"34s"`` or ``"1.5s"``."""
    match = _DURATION.match(str(value)) if value is not None else None
    return float(match["seconds"]) if match else None
