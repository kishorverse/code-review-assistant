"""Chooses a provider for each request and falls back when one cannot serve it.

For every request the router walks the task's preference list. A provider is
passed over when the request forbids it, when its circuit breaker is open, or
when its rate limits would make the request wait too long. Otherwise the router
reserves rate-limit capacity, calls it and, on failure, pauses it for as long
as the failure suggests before trying the next one. Every attempt produces a
:class:`~app.llm.models.CallRecord`.
"""

import asyncio
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from app.errors import (
    AllProvidersUnavailableError,
    ProviderAuthError,
    ProviderError,
    ProviderRequestError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.llm.breaker import BreakerState, BreakerStatus, CircuitBreaker
from app.llm.cache import ResponseCache
from app.llm.clock import Clock
from app.llm.limits import RateLimiter
from app.llm.models import CallRecord, CallStatus, LLMRequest, LLMResponse, Priority, Task
from app.llm.providers.base import LLMProvider

QUOTA_COOLDOWN_SECONDS = 3_600.0
"""How long to pause a provider whose quota ran out without saying when it resets."""

AUTH_COOLDOWN_SECONDS = 3_600.0
"""A rejected key will not start working by itself, so the provider is paused for long."""

OnCall = Callable[[CallRecord], None]


@dataclass(frozen=True)
class RoutedProvider:
    """A provider with the state the router keeps for it.

    Attributes:
        provider: The client.
        limiter: Rate-limit budget; providers on one account may share a limiter.
        breaker: Health of this provider.
        semaphore: Caps concurrent calls.
        timeout_seconds: Upper bound on one call, including reading the response.
    """

    provider: LLMProvider
    limiter: RateLimiter
    breaker: CircuitBreaker
    semaphore: asyncio.Semaphore
    timeout_seconds: float


@dataclass(frozen=True)
class ProviderStatus:
    """What the providers page shows for one provider."""

    name: str
    model: str
    external: bool
    breaker: BreakerStatus


@dataclass(frozen=True)
class _Outcome:
    response: LLMResponse | None
    record: CallRecord


class Router:
    """Routes requests across providers with rate limiting, circuit breaking and caching."""

    def __init__(
        self,
        providers: Sequence[RoutedProvider],
        routing: Mapping[Task, Sequence[str]],
        *,
        clock: Clock,
        cache: ResponseCache,
        max_wait_seconds: Mapping[Priority, float],
    ) -> None:
        self._providers = {routed.provider.name: routed for routed in providers}
        self._routing = routing
        self._clock = clock
        self._cache = cache
        self._max_wait_seconds = max_wait_seconds

    async def complete(self, request: LLMRequest, on_call: OnCall | None = None) -> LLMResponse:
        """Complete a request with the first provider that can serve it.

        Args:
            request: The prompt and its routing constraints.
            on_call: Receives a record of every attempt, for progress and provenance.

        Raises:
            AllProvidersUnavailableError: If no eligible provider succeeded.
        """
        cached = self._cache.get(request)
        if cached is not None and self._may_serve(cached.provider, request):
            _notify(on_call, _record(request, cached.provider, cached.model, CallStatus.CACHED))
            return cached

        attempts: list[CallRecord] = []
        for routed in self._candidates(request):
            outcome = await self._attempt(routed, request)
            attempts.append(outcome.record)
            _notify(on_call, outcome.record)
            if outcome.response is not None:
                self._cache.put(request, outcome.response)
                return outcome.response
        raise AllProvidersUnavailableError(request.task, attempts)

    def status(self) -> list[ProviderStatus]:
        """The enabled providers and the health of each."""
        return [
            ProviderStatus(
                name=name,
                model=routed.provider.model,
                external=routed.provider.external,
                breaker=routed.breaker.status(),
            )
            for name, routed in self._providers.items()
        ]

    def _candidates(self, request: LLMRequest) -> Iterator[RoutedProvider]:
        order = list(self._routing.get(request.task, ()))
        if request.only_providers is not None:
            # An explicit restriction may name a provider outside the task's usual route.
            order += sorted(request.only_providers - set(order))
        for name in order:
            routed = self._providers.get(name)
            if routed is not None and self._permits(name, routed.provider.external, request):
                yield routed

    def _may_serve(self, name: str, request: LLMRequest) -> bool:
        routed = self._providers.get(name)
        return routed is not None and self._permits(name, routed.provider.external, request)

    @staticmethod
    def _permits(name: str, external: bool, request: LLMRequest) -> bool:
        if name in request.exclude_providers:
            return False
        if request.only_providers is not None and name not in request.only_providers:
            return False
        return request.allow_external or not external

    async def _attempt(self, routed: RoutedProvider, request: LLMRequest) -> _Outcome:
        tokens = request.estimated_tokens()
        refusal, wait = self._admission(routed, request, tokens)
        if refusal is not None:
            return self._skip(routed, request, refusal)
        routed.limiter.reserve(tokens)
        if wait > 0:
            await self._clock.sleep(wait)
        async with routed.semaphore:
            if routed.breaker.state is BreakerState.OPEN:
                # Another call failed while this one waited; sending it too would pile on.
                routed.limiter.refund_tokens(tokens)
                return self._skip(routed, request, f"paused: {routed.breaker.status().reason}")
            return await self._call(routed, request, tokens)

    def _admission(
        self, routed: RoutedProvider, request: LLMRequest, tokens: int
    ) -> tuple[str | None, float]:
        """Why the provider cannot take the request, if it cannot, and the rate-limit wait."""
        breaker = routed.breaker
        if breaker.state is BreakerState.OPEN:
            return f"paused: {breaker.status().reason}", 0.0
        wait = routed.limiter.wait_time(tokens)
        if wait > self._max_wait_seconds[request.priority]:
            return f"rate limit would delay the call {wait:.0f}s", wait
        # Checked last because a half-open breaker hands out a single probe.
        if not breaker.allows():
            return "a recovery probe is already in flight", wait
        return None, wait

    async def _call(self, routed: RoutedProvider, request: LLMRequest, tokens: int) -> _Outcome:
        provider = routed.provider
        started = self._clock.monotonic()
        try:
            async with asyncio.timeout(routed.timeout_seconds):
                response = await provider.complete(request)
        except (ProviderError, TimeoutError) as error:
            status, refused = self._record_failure(routed.breaker, error)
            if refused:
                routed.limiter.refund_tokens(tokens)
            latency_ms = round((self._clock.monotonic() - started) * 1000)
            detail = str(error) or "call timed out"
            record = _record(request, provider.name, provider.model, status, detail, latency_ms)
            return _Outcome(None, record)

        routed.breaker.record_success()
        used = response.input_tokens + response.output_tokens
        if used:
            routed.limiter.refund_tokens(tokens - used)
        record = CallRecord(
            task=request.task,
            provider=provider.name,
            model=response.model,
            status=CallStatus.OK,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        return _Outcome(response, record)

    @staticmethod
    def _record_failure(
        breaker: CircuitBreaker, error: ProviderError | TimeoutError
    ) -> tuple[CallStatus, bool]:
        """Pause the provider as the failure warrants.

        Returns:
            The call status, and whether the provider refused the request outright,
            in which case the reserved tokens were not spent.
        """
        if isinstance(error, RateLimitedError):
            breaker.record_rate_limit(error.retry_after)
            return CallStatus.RATE_LIMITED, True
        if isinstance(error, QuotaExhaustedError):
            if error.resets_at is not None:
                breaker.open_until(error.resets_at, "quota used up")
            else:
                breaker.open_for(QUOTA_COOLDOWN_SECONDS, "quota used up")
            return CallStatus.QUOTA_EXHAUSTED, True
        if isinstance(error, ProviderAuthError):
            breaker.open_for(AUTH_COOLDOWN_SECONDS, "API key rejected")
            return CallStatus.AUTH_FAILED, True
        if isinstance(error, ProviderRequestError):
            breaker.record_failure("requests rejected")
            return CallStatus.REJECTED, False
        breaker.record_failure("unavailable")
        return CallStatus.UNAVAILABLE, False

    @staticmethod
    def _skip(routed: RoutedProvider, request: LLMRequest, detail: str) -> _Outcome:
        provider = routed.provider
        return _Outcome(
            None, _record(request, provider.name, provider.model, CallStatus.SKIPPED, detail)
        )


def _record(
    request: LLMRequest,
    provider: str,
    model: str,
    status: CallStatus,
    detail: str | None = None,
    latency_ms: int = 0,
) -> CallRecord:
    return CallRecord(
        task=request.task,
        provider=provider,
        model=model,
        status=status,
        latency_ms=latency_ms,
        detail=detail,
    )


def _notify(on_call: OnCall | None, record: CallRecord) -> None:
    if on_call is not None:
        on_call(record)
