"""Chooses a provider for each request and falls back when one cannot serve it.

For every request the router walks the task's preference list. A provider is
passed over when the request forbids it, when its circuit breaker is open, or
when its rate limits would make the request wait too long. Otherwise the router
reserves rate-limit capacity, waits for it and for a concurrency slot, and only
then asks the breaker whether to call: the provider may have been paused while
the request waited. On failure the provider is paused for as long as the
failure suggests before the next one is tried. Every attempt produces a
:class:`~app.llm.models.CallRecord`.
"""

import asyncio
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from app.errors import (
    AllProvidersUnavailableError,
    InvalidResponseError,
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderRequestError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.llm.breaker import BreakerState, BreakerStatus, CircuitBreaker
from app.llm.cache import ResponseCache
from app.llm.clock import Clock
from app.llm.limits import RateLimiter, Reservation
from app.llm.models import CallRecord, CallStatus, LLMRequest, LLMResponse, Priority, Task
from app.llm.providers.base import LLMProvider

QUOTA_COOLDOWN_SECONDS = 3_600.0
"""How long to pause a provider whose quota ran out without saying when it resets."""

CONFIG_COOLDOWN_SECONDS = 3_600.0
"""A rejected key or a wrong model id will not fix itself, so the provider is paused for long."""

_REFUSED = frozenset(
    {
        CallStatus.RATE_LIMITED,
        CallStatus.QUOTA_EXHAUSTED,
        CallStatus.AUTH_FAILED,
        CallStatus.MISCONFIGURED,
    }
)
"""Failures where the provider did not process the request, so its tokens were not spent."""

OnCall = Callable[[CallRecord], None]

Validator = Callable[[LLMResponse], None]
"""Raises :class:`~app.errors.InvalidResponseError` for an answer the caller cannot use."""


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

    async def complete(
        self,
        request: LLMRequest,
        on_call: OnCall | None = None,
        validate: Validator | None = None,
    ) -> LLMResponse:
        """Complete a request with the first provider that gives a usable answer.

        Args:
            request: The prompt and its routing constraints.
            on_call: Receives a record of every attempt, for progress and provenance.
            validate: Checks each answer. An answer it rejects counts as a rejected
                request: the next provider is tried and the answer is not cached.

        Raises:
            AllProvidersUnavailableError: If no eligible provider succeeded.
        """
        cached = self._cache.get(request)
        if (
            cached is not None
            and self._may_serve(cached.provider, request)
            and _is_usable(cached, validate)
        ):
            _notify(on_call, _record(request, cached.provider, cached.model, CallStatus.CACHED))
            return cached

        attempts: list[CallRecord] = []
        for routed in self._candidates(request):
            outcome = await self._attempt(routed, request, validate)
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

    async def _attempt(
        self, routed: RoutedProvider, request: LLMRequest, validate: Validator | None
    ) -> _Outcome:
        breaker, limiter = routed.breaker, routed.limiter
        if breaker.state is BreakerState.OPEN:
            return self._skip(routed, request, _refusal(breaker))
        tokens = request.estimated_tokens()
        max_wait = self._max_wait_seconds[request.priority]
        wait = limiter.wait_time(tokens)
        if wait > max_wait:
            return self._skip(routed, request, f"rate limit would delay the call {wait:.0f}s")

        reservation = limiter.reserve(tokens)
        if wait > 0:
            await self._clock.sleep(wait)
        # Batch work queues for a slot; interactive requests move on within their wait budget.
        slot_wait = max_wait - wait if request.priority is Priority.INTERACTIVE else None
        if not await _acquire(routed.semaphore, slot_wait):
            limiter.cancel(reservation)
            return self._skip(routed, request, "every concurrent slot is busy")
        try:
            # Asked only now: the provider may have been paused while this request
            # waited, and a recovering provider must receive a single probe.
            if not breaker.allows():
                limiter.cancel(reservation)
                return self._skip(routed, request, _refusal(breaker))
            return await self._call(routed, request, reservation, validate)
        finally:
            routed.semaphore.release()

    async def _call(
        self,
        routed: RoutedProvider,
        request: LLMRequest,
        reservation: Reservation,
        validate: Validator | None,
    ) -> _Outcome:
        provider = routed.provider
        started = self._clock.monotonic()
        try:
            async with asyncio.timeout(routed.timeout_seconds):
                response = await provider.complete(request)
            if validate is not None:
                validate(response)
        except (ProviderError, TimeoutError) as error:
            status = self._record_failure(routed.breaker, error)
            if status in _REFUSED:
                routed.limiter.settle(reservation, used_tokens=0)
            latency_ms = round((self._clock.monotonic() - started) * 1000)
            detail = str(error) or "call timed out"
            record = _record(request, provider.name, provider.model, status, detail, latency_ms)
            return _Outcome(None, record)

        routed.breaker.record_success()
        used = response.input_tokens + response.output_tokens
        if used:
            routed.limiter.settle(reservation, used)
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
    def _record_failure(breaker: CircuitBreaker, error: ProviderError | TimeoutError) -> CallStatus:
        """Pause the provider as the failure warrants."""
        if isinstance(error, RateLimitedError):
            breaker.record_rate_limit(error.retry_after)
            return CallStatus.RATE_LIMITED
        if isinstance(error, QuotaExhaustedError):
            if error.resets_at is not None:
                breaker.open_until(error.resets_at, "quota used up")
            else:
                breaker.open_for(QUOTA_COOLDOWN_SECONDS, "quota used up")
            return CallStatus.QUOTA_EXHAUSTED
        if isinstance(error, ProviderAuthError):
            breaker.open_for(CONFIG_COOLDOWN_SECONDS, "API key rejected")
            return CallStatus.AUTH_FAILED
        if isinstance(error, ProviderConfigError):
            breaker.open_for(CONFIG_COOLDOWN_SECONDS, "check the model id and base URL")
            return CallStatus.MISCONFIGURED
        if isinstance(error, ProviderRequestError):
            # About this request only; pausing the provider would fail requests it can serve.
            breaker.record_rejection()
            return CallStatus.REJECTED
        breaker.record_failure("unavailable")
        return CallStatus.UNAVAILABLE

    @staticmethod
    def _skip(routed: RoutedProvider, request: LLMRequest, detail: str) -> _Outcome:
        provider = routed.provider
        return _Outcome(
            None, _record(request, provider.name, provider.model, CallStatus.SKIPPED, detail)
        )


async def _acquire(semaphore: asyncio.Semaphore, max_wait_seconds: float | None) -> bool:
    """Take a concurrency slot, giving up after ``max_wait_seconds`` when a limit is given."""
    if max_wait_seconds is None or not semaphore.locked():
        await semaphore.acquire()
        return True
    try:
        async with asyncio.timeout(max_wait_seconds):
            await semaphore.acquire()
    except TimeoutError:
        return False
    return True


def _is_usable(response: LLMResponse, validate: Validator | None) -> bool:
    if validate is None:
        return True
    try:
        validate(response)
    except InvalidResponseError:
        return False
    return True


def _refusal(breaker: CircuitBreaker) -> str:
    if breaker.state is BreakerState.OPEN:
        return f"paused: {breaker.status().reason}"
    return "a recovery probe is already in flight"


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
