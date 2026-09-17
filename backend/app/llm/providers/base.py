"""The provider contract and HTTP helpers shared by provider clients.

Providers are called over plain HTTPS with ``httpx`` rather than vendor SDKs:
one client for every provider means uniform timeouts, no hidden retries
competing with the router, precise error mapping, and fewer dependencies.
"""

import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx

from app.errors import (
    ProviderAuthError,
    ProviderRequestError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.llm.models import LLMRequest, LLMResponse

MAX_ERROR_DETAIL = 200


class LLMProvider(Protocol):
    """A model endpoint the router can call."""

    @property
    def name(self) -> str:
        """Stable provider name used in configuration, findings and records."""
        ...

    @property
    def model(self) -> str:
        """The model id requests are sent to."""
        ...

    @property
    def external(self) -> bool:
        """Whether requests leave this machine, which requires the user's consent."""
        ...

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one request.

        Raises:
            RateLimitedError, QuotaExhaustedError, ProviderAuthError,
            ProviderUnavailableError, ProviderRequestError: As appropriate.
        """
        ...


async def post_json(
    client: httpx.AsyncClient,
    provider: str,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_seconds: float,
) -> tuple[httpx.Response, int]:
    """POST a JSON body, returning the response and the latency in milliseconds.

    Raises:
        ProviderUnavailableError: On timeouts and connection failures.
    """
    started = time.perf_counter()
    try:
        response = await client.post(url, headers=headers, json=body, timeout=timeout_seconds)
    except httpx.TimeoutException as error:
        raise ProviderUnavailableError(provider, "request timed out") from error
    except httpx.HTTPError as error:
        raise ProviderUnavailableError(
            provider, f"connection failed ({type(error).__name__})"
        ) from error
    return response, round((time.perf_counter() - started) * 1000)


def raise_for_status(provider: str, response: httpx.Response, now: datetime) -> None:
    """Map an unsuccessful HTTP status onto the provider error the router expects."""
    status = response.status_code
    if status < 400:
        return
    detail = error_detail(response)
    if status == 429:
        retry_after = parse_retry_after(response.headers.get("retry-after"), now)
        raise RateLimitedError(provider, f"rate limited: {detail}", retry_after=retry_after)
    if status == 402:
        raise QuotaExhaustedError(provider, f"credits exhausted: {detail}")
    if status in (401, 403):
        raise ProviderAuthError(provider, f"authentication failed (HTTP {status}): {detail}")
    if status == 408 or status >= 500:
        raise ProviderUnavailableError(provider, f"HTTP {status}: {detail}")
    raise ProviderRequestError(provider, f"HTTP {status}: {detail}")


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    """Seconds from a ``Retry-After`` header given as seconds or as an HTTP date."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(value) - now).total_seconds())
    except (TypeError, ValueError):
        return None


def error_detail(response: httpx.Response) -> str:
    """A short explanation from an error body, without echoing large payloads."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:MAX_ERROR_DETAIL] or response.reason_phrase
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
    elif isinstance(error, str):
        message = error
    else:
        message = None
    return str(message or response.reason_phrase)[:MAX_ERROR_DETAIL]


def usage_count(usage: object, key: str) -> int:
    """A token count from a usage block, or 0 when the provider omits or garbles it."""
    value = usage.get(key) if isinstance(usage, dict) else None
    return value if isinstance(value, int) and value >= 0 else 0


def json_object(provider: str, response: httpx.Response) -> dict[str, Any]:
    """Decode a successful response body that must be a JSON object.

    Raises:
        ProviderRequestError: If the body is not a JSON object.
    """
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderRequestError(provider, "response was not JSON") from error
    if not isinstance(payload, dict):
        raise ProviderRequestError(provider, "response was not a JSON object")
    return payload
