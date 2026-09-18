import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta

import pytest

from app.errors import (
    AllProvidersUnavailableError,
    InvalidResponseError,
    ProviderAuthError,
    ProviderConfigError,
    ProviderRequestError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.llm.breaker import BreakerState, CircuitBreaker
from app.llm.cache import ResponseCache
from app.llm.limits import RateLimiter, RateLimits
from app.llm.models import CallRecord, CallStatus, LLMRequest, LLMResponse, Priority, Task
from app.llm.router import RoutedProvider, Router
from tests.llm.conftest import FakeClock

Step = BaseException | Callable[[], Awaitable[None]]


class ScriptedProvider:
    """Plays back failures in order, then succeeds."""

    def __init__(
        self,
        name: str,
        *steps: Step,
        external: bool = False,
        model: str = "m",
        reports_model: str | None = None,
    ) -> None:
        self._name = name
        self._model = model
        self._reports_model = reports_model or model
        self._external = external
        self._steps = list(steps)
        self.calls = 0
        self.active = 0
        self.max_active = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def external(self) -> bool:
        return self._external

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            step = self._steps.pop(0) if self._steps else None
            if isinstance(step, BaseException):
                raise step
            if step is not None:
                await step()
        finally:
            self.active -= 1
        return LLMResponse(
            text=f"answer from {self._name}",
            provider=self._name,
            model=self._reports_model,
            input_tokens=10,
            output_tokens=5,
            latency_ms=120,
        )


def routed(
    provider: ScriptedProvider,
    clock: FakeClock,
    *,
    limits: RateLimits | None = None,
    limiter: RateLimiter | None = None,
    concurrency: int = 4,
    timeout_seconds: float = 5.0,
) -> RoutedProvider:
    return RoutedProvider(
        provider=provider,
        limiter=limiter or RateLimiter(limits or RateLimits(), clock),
        breaker=CircuitBreaker(clock),
        semaphore=asyncio.Semaphore(concurrency),
        timeout_seconds=timeout_seconds,
    )


def make_router(
    clock: FakeClock,
    *providers: RoutedProvider,
    cache_entries: int = 0,
    interactive_wait: float = 5.0,
) -> Router:
    order = [entry.provider.name for entry in providers]
    return Router(
        providers,
        dict.fromkeys(Task, tuple(order)),
        clock=clock,
        cache=ResponseCache(cache_entries),
        max_wait_seconds={Priority.INTERACTIVE: interactive_wait, Priority.BATCH: 30.0},
    )


def request(**changes: object) -> LLMRequest:
    base = LLMRequest(task=Task.REVIEW, system="system", user="code", max_output_tokens=100)
    return base.model_copy(update=changes)


def statuses(records: list[CallRecord]) -> list[tuple[str, CallStatus]]:
    return [(record.provider, record.status) for record in records]


async def test_uses_the_first_preference_and_reports_the_call(clock: FakeClock) -> None:
    first, second = ScriptedProvider("nvidia"), ScriptedProvider("gemini")
    router = make_router(clock, routed(first, clock), routed(second, clock))
    records: list[CallRecord] = []

    response = await router.complete(request(), on_call=records.append)

    assert response.provider == "nvidia"
    assert (first.calls, second.calls) == (1, 0)
    assert statuses(records) == [("nvidia", CallStatus.OK)]
    assert (records[0].input_tokens, records[0].output_tokens, records[0].latency_ms) == (
        10,
        5,
        120,
    )


async def test_falls_back_to_the_next_provider(clock: FakeClock) -> None:
    failing = ScriptedProvider("nvidia", ProviderUnavailableError("nvidia", "HTTP 503"))
    router = make_router(clock, routed(failing, clock), routed(ScriptedProvider("local"), clock))
    records: list[CallRecord] = []

    response = await router.complete(request(), on_call=records.append)

    assert response.provider == "local"
    assert statuses(records) == [("nvidia", CallStatus.UNAVAILABLE), ("local", CallStatus.OK)]
    assert records[0].detail == "nvidia: HTTP 503"


async def test_external_providers_need_consent(clock: FakeClock) -> None:
    hosted = ScriptedProvider("gemini", external=True)
    local = ScriptedProvider("local")
    router = make_router(clock, routed(hosted, clock), routed(local, clock))

    private = await router.complete(request())
    consented = await router.complete(request(allow_external=True))

    assert (private.provider, consented.provider) == ("local", "gemini")


async def test_without_consent_or_local_model_nothing_is_sent(clock: FakeClock) -> None:
    hosted = ScriptedProvider("gemini", external=True)
    router = make_router(clock, routed(hosted, clock))

    with pytest.raises(AllProvidersUnavailableError, match="none enabled") as caught:
        await router.complete(request())

    assert hosted.calls == 0
    assert caught.value.attempts == []


async def test_excluded_providers_are_never_called(clock: FakeClock) -> None:
    reviewer, verifier = ScriptedProvider("nvidia"), ScriptedProvider("gemini")
    router = make_router(clock, routed(reviewer, clock), routed(verifier, clock))

    response = await router.complete(
        request(task=Task.VERIFY, exclude_providers=frozenset({"nvidia"}))
    )

    assert response.provider == "gemini"
    assert reviewer.calls == 0


async def test_only_providers_restricts_and_can_leave_the_usual_route(clock: FakeClock) -> None:
    usual, small = ScriptedProvider("nvidia"), ScriptedProvider("hf-small")
    router = Router(
        [routed(usual, clock), routed(small, clock)],
        dict.fromkeys(Task, ("nvidia",)),
        clock=clock,
        cache=ResponseCache(0),
        max_wait_seconds={Priority.INTERACTIVE: 5.0, Priority.BATCH: 30.0},
    )

    response = await router.complete(request(only_providers=frozenset({"hf-small"})))

    assert response.provider == "hf-small"
    assert usual.calls == 0


async def test_raises_with_every_attempt_when_all_providers_fail(clock: FakeClock) -> None:
    router = make_router(
        clock,
        routed(ScriptedProvider("nvidia", ProviderAuthError("nvidia", "bad key")), clock),
        routed(ScriptedProvider("local", ProviderRequestError("local", "no model")), clock),
    )

    with pytest.raises(AllProvidersUnavailableError) as caught:
        await router.complete(request())

    assert caught.value.task is Task.REVIEW
    assert statuses(caught.value.attempts) == [
        ("nvidia", CallStatus.AUTH_FAILED),
        ("local", CallStatus.REJECTED),
    ]
    assert "nvidia: auth_failed" in str(caught.value)


async def test_rate_limited_provider_is_paused_for_the_requested_delay(clock: FakeClock) -> None:
    limited = ScriptedProvider("nvidia", RateLimitedError("nvidia", "slow down", retry_after=20))
    router = make_router(clock, routed(limited, clock), routed(ScriptedProvider("local"), clock))
    await router.complete(request())
    records: list[CallRecord] = []

    await router.complete(request(), on_call=records.append)
    clock.advance(21)
    recovered = await router.complete(request())

    assert statuses(records) == [("nvidia", CallStatus.SKIPPED), ("local", CallStatus.OK)]
    assert records[0].detail == "paused: rate limited"
    assert recovered.provider == "nvidia"
    assert limited.calls == 2


async def test_daily_quota_pauses_until_the_reset_time(clock: FakeClock) -> None:
    resets_at = clock.now() + timedelta(hours=23)
    gemini = ScriptedProvider("gemini", QuotaExhaustedError("gemini", "daily", resets_at=resets_at))
    router = make_router(clock, routed(gemini, clock), routed(ScriptedProvider("local"), clock))
    await router.complete(request())

    clock.advance(timedelta(hours=22).total_seconds())
    still_paused = await router.complete(request())
    clock.advance(timedelta(hours=1, seconds=1).total_seconds())
    reset = await router.complete(request())

    assert (still_paused.provider, reset.provider) == ("local", "gemini")


async def test_quota_without_a_reset_time_pauses_for_an_hour(clock: FakeClock) -> None:
    hf = ScriptedProvider("hf-large", QuotaExhaustedError("hf-large", "credits exhausted"))
    router = make_router(clock, routed(hf, clock), routed(ScriptedProvider("local"), clock))
    await router.complete(request())

    clock.advance(3_599)
    assert (await router.complete(request())).provider == "local"
    clock.advance(2)
    assert (await router.complete(request())).provider == "hf-large"


async def test_rejected_key_pauses_the_provider(clock: FakeClock) -> None:
    entry = routed(ScriptedProvider("nvidia", ProviderAuthError("nvidia", "401")), clock)
    router = make_router(clock, entry, routed(ScriptedProvider("local"), clock))

    await router.complete(request())

    [status, _] = router.status()
    assert (status.name, status.breaker.state, status.breaker.reason) == (
        "nvidia",
        BreakerState.OPEN,
        "API key rejected",
    )
    assert status.breaker.reopens_in_seconds == 3_600


async def test_repeated_failures_open_the_breaker(clock: FakeClock) -> None:
    down = ProviderUnavailableError("nvidia", "HTTP 502")
    flaky = ScriptedProvider("nvidia", down, down, down)
    router = make_router(clock, routed(flaky, clock), routed(ScriptedProvider("local"), clock))

    for _ in range(4):
        await router.complete(request())

    assert flaky.calls == 3
    assert router.status()[0].breaker.state is BreakerState.OPEN


async def test_batch_requests_wait_briefly_for_rate_limit_capacity(clock: FakeClock) -> None:
    limits = RateLimits(requests_per_minute=3, safety=1.0)
    nvidia = ScriptedProvider("nvidia")
    router = make_router(
        clock, routed(nvidia, clock, limits=limits), routed(ScriptedProvider("local"), clock)
    )

    responses = [await router.complete(request()) for _ in range(3)]
    clock.advance(40)
    responses.append(await router.complete(request()))

    assert [response.provider for response in responses] == ["nvidia"] * 4
    assert clock.sleeps == [pytest.approx(20.0)], "until the first request leaves the window"


async def test_requests_move_on_when_the_wait_is_too_long(clock: FakeClock) -> None:
    limits = RateLimits(requests_per_minute=1, safety=1.0)
    router = make_router(
        clock,
        routed(ScriptedProvider("nvidia"), clock, limits=limits),
        routed(ScriptedProvider("local"), clock),
    )
    await router.complete(request())
    records: list[CallRecord] = []

    interactive = await router.complete(
        request(priority=Priority.INTERACTIVE), on_call=records.append
    )

    assert interactive.provider == "local"
    assert records[0].detail == "rate limit would delay the call 60s"
    assert clock.sleeps == []


async def test_unused_reserved_tokens_are_returned(clock: FakeClock) -> None:
    limiter = RateLimiter(RateLimits(tokens_per_minute=150, safety=1.0), clock)
    router = make_router(clock, routed(ScriptedProvider("nvidia"), clock, limiter=limiter))

    await router.complete(request())

    # The estimate reserved 103 tokens; the provider reported using 15.
    assert limiter.wait_time(150 - 15) == 0.0


async def test_tokens_of_a_refused_request_are_returned(clock: FakeClock) -> None:
    limiter = RateLimiter(RateLimits(tokens_per_minute=150, safety=1.0), clock)
    refused = ScriptedProvider("nvidia", RateLimitedError("nvidia", "429"))
    router = make_router(
        clock, routed(refused, clock, limiter=limiter), routed(ScriptedProvider("local"), clock)
    )

    await router.complete(request())

    assert limiter.wait_time(150) == 0.0


async def test_a_call_that_waited_is_dropped_if_the_provider_was_paused_meanwhile(
    clock: FakeClock,
) -> None:
    limiter = RateLimiter(RateLimits(requests_per_minute=4, safety=1.0), clock)
    for _ in range(4):
        limiter.reserve(0)
    clock.advance(45)
    nvidia = ScriptedProvider("nvidia")
    entry = routed(nvidia, clock, limiter=limiter)
    router = make_router(clock, entry, routed(ScriptedProvider("local"), clock))

    async def another_call_fails_meanwhile(seconds: float) -> None:
        clock.sleeps.append(seconds)
        clock.advance(seconds)
        entry.breaker.open_for(30, "rate limited")

    clock.sleep = another_call_fails_meanwhile
    records: list[CallRecord] = []
    response = await router.complete(request(), on_call=records.append)

    assert clock.sleeps == [pytest.approx(15.0)]
    assert response.provider == "local"
    assert nvidia.calls == 0
    assert limiter.wait_time(0) == 0.0, "the unsent request gives its slot back"
    assert (records[0].status, records[0].detail) == (CallStatus.SKIPPED, "paused: rate limited")


async def test_a_request_that_waited_does_not_take_a_second_probe(clock: FakeClock) -> None:
    limiter = RateLimiter(RateLimits(requests_per_minute=4, safety=1.0), clock)
    for _ in range(4):
        limiter.reserve(0)
    clock.advance(45)
    nvidia = ScriptedProvider("nvidia")
    entry = routed(nvidia, clock, limiter=limiter)
    router = make_router(clock, entry, routed(ScriptedProvider("local"), clock))

    async def paused_and_probed_meanwhile(seconds: float) -> None:
        entry.breaker.open_for(2, "rate limited")
        clock.advance(seconds)
        assert entry.breaker.allows(), "another request takes the probe"

    clock.sleep = paused_and_probed_meanwhile
    records: list[CallRecord] = []
    response = await router.complete(request(), on_call=records.append)

    assert response.provider == "local"
    assert nvidia.calls == 0
    assert records[0].detail == "a recovery probe is already in flight"


async def test_a_success_that_lands_after_a_quota_error_keeps_the_pause(clock: FakeClock) -> None:
    release = asyncio.Event()
    quota = QuotaExhaustedError("gemini", "daily", resets_at=clock.now() + timedelta(hours=12))
    gemini = ScriptedProvider("gemini", release.wait, quota)
    router = make_router(clock, routed(gemini, clock), routed(ScriptedProvider("local"), clock))

    slow = asyncio.create_task(router.complete(request(user="slow")))
    await asyncio.sleep(0)
    await router.complete(request(user="fast"))
    release.set()
    await slow
    later = await router.complete(request(user="later"))

    [status, _] = router.status()
    assert (status.breaker.state, status.breaker.reason) == (BreakerState.OPEN, "quota used up")
    assert later.provider == "local"
    assert gemini.calls == 2


async def test_rejected_requests_do_not_pause_the_provider(clock: FakeClock) -> None:
    too_long = ProviderRequestError("nvidia", "context too long")
    nvidia = ScriptedProvider("nvidia", too_long, too_long, too_long, too_long)
    router = make_router(clock, routed(nvidia, clock), routed(ScriptedProvider("local"), clock))

    providers = [(await router.complete(request(user=str(n)))).provider for n in range(5)]

    assert providers == ["local"] * 4 + ["nvidia"]
    assert nvidia.calls == 5
    assert router.status()[0].breaker.state is BreakerState.CLOSED


async def test_wrong_model_id_pauses_the_provider_as_misconfigured(clock: FakeClock) -> None:
    missing = ProviderConfigError("nvidia", "model or endpoint not found: unknown model")
    router = make_router(
        clock,
        routed(ScriptedProvider("nvidia", missing), clock),
        routed(ScriptedProvider("local"), clock),
    )
    records: list[CallRecord] = []

    await router.complete(request(), on_call=records.append)

    [status, _] = router.status()
    assert records[0].status is CallStatus.MISCONFIGURED
    assert status.breaker.reason == "check the model id and base URL"
    assert status.breaker.reopens_in_seconds == 3_600


async def test_interactive_requests_do_not_queue_behind_a_busy_provider(clock: FakeClock) -> None:
    release = asyncio.Event()
    local = ScriptedProvider("local", release.wait)
    fallback = ScriptedProvider("nvidia")
    router = make_router(
        clock, routed(local, clock, concurrency=1), routed(fallback, clock), interactive_wait=0.01
    )

    batch = asyncio.create_task(router.complete(request(user="batch")))
    await asyncio.sleep(0)
    records: list[CallRecord] = []
    async with asyncio.timeout(2):  # Fails fast instead of hanging if the request queues.
        interactive = await router.complete(
            request(user="interactive", priority=Priority.INTERACTIVE), on_call=records.append
        )
    release.set()
    await batch

    assert interactive.provider == "nvidia"
    assert records[0].detail == "every concurrent slot is busy"
    assert local.calls == 1


async def test_half_open_breaker_lets_one_probe_through(clock: FakeClock) -> None:
    release = asyncio.Event()
    probe = ScriptedProvider(
        "nvidia", RateLimitedError("nvidia", "429", retry_after=10), release.wait
    )
    local = ScriptedProvider("local")
    router = make_router(clock, routed(probe, clock), routed(local, clock))
    await router.complete(request())
    clock.advance(11)

    probing = asyncio.create_task(router.complete(request()))
    await asyncio.sleep(0)
    records: list[CallRecord] = []
    meanwhile = await router.complete(request(), on_call=records.append)
    release.set()
    probed = await probing

    assert (probed.provider, meanwhile.provider) == ("nvidia", "local")
    assert records[0].detail == "a recovery probe is already in flight"
    assert router.status()[0].breaker.state is BreakerState.CLOSED


async def test_concurrency_is_capped_per_provider(clock: FakeClock) -> None:
    gate = asyncio.Event()
    nvidia = ScriptedProvider("nvidia", gate.wait, gate.wait, gate.wait)
    router = make_router(clock, routed(nvidia, clock, concurrency=2))

    calls = asyncio.gather(*(router.complete(request(user=str(n))) for n in range(3)))
    await asyncio.sleep(0)
    gate.set()
    await calls

    assert nvidia.max_active == 2


async def test_slow_calls_time_out_and_count_as_unavailable(clock: FakeClock) -> None:
    async def hang() -> None:
        await asyncio.sleep(10)

    slow = ScriptedProvider("local", hang)
    router = make_router(clock, routed(slow, clock, timeout_seconds=0.01))

    with pytest.raises(AllProvidersUnavailableError) as caught:
        await router.complete(request())

    [record] = caught.value.attempts
    assert (record.status, record.detail) == (CallStatus.UNAVAILABLE, "call timed out")


async def test_repeated_requests_are_served_from_the_cache(clock: FakeClock) -> None:
    nvidia = ScriptedProvider("nvidia")
    router = make_router(clock, routed(nvidia, clock), cache_entries=8)
    await router.complete(request())
    records: list[CallRecord] = []

    again = await router.complete(request(), on_call=records.append)

    assert nvidia.calls == 1
    assert again.cached
    assert statuses(records) == [("nvidia", CallStatus.CACHED)]


@pytest.mark.parametrize(
    "constraint",
    [
        {"allow_external": False},
        {"exclude_providers": frozenset({"nvidia"})},
        {"only_providers": frozenset({"local"})},
    ],
)
async def test_cached_answers_respect_the_routing_constraints(
    clock: FakeClock, constraint: dict[str, object]
) -> None:
    hosted, local = ScriptedProvider("nvidia", external=True), ScriptedProvider("local")
    router = make_router(clock, routed(hosted, clock), routed(local, clock), cache_entries=8)
    await router.complete(request(allow_external=True))

    answer = await router.complete(request(**({"allow_external": True} | constraint)))

    assert (answer.provider, answer.cached) == ("local", False)
    assert (hosted.calls, local.calls) == (1, 1)


async def test_cache_hits_do_not_depend_on_the_reported_model_version(clock: FakeClock) -> None:
    gemini = ScriptedProvider("gemini", model="gemini-flash", reports_model="gemini-flash-001")
    router = make_router(clock, routed(gemini, clock), cache_entries=8)
    await router.complete(request())

    again = await router.complete(request())

    assert (again.cached, again.model, gemini.calls) == (True, "gemini-flash-001", 1)


async def test_status_lists_enabled_providers(clock: FakeClock) -> None:
    router = make_router(
        clock,
        routed(ScriptedProvider("gemini", external=True, model="flash"), clock),
        routed(ScriptedProvider("local", model="qwen"), clock),
    )

    [gemini, local] = router.status()

    assert (gemini.name, gemini.model, gemini.external) == ("gemini", "flash", True)
    assert (local.name, local.model, local.external) == ("local", "qwen", False)
    assert local.breaker.state is BreakerState.CLOSED


def json_only(response: LLMResponse) -> None:
    if not response.text.startswith("{"):
        raise InvalidResponseError(response.provider, "answer was not JSON")


class TextProvider(ScriptedProvider):
    """Answers with fixed text."""

    def __init__(self, name: str, text: str) -> None:
        super().__init__(name)
        self._text = text

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await super().complete(request)
        return response.model_copy(update={"text": self._text})


async def test_unusable_answers_fall_back_and_are_not_cached(clock: FakeClock) -> None:
    rambling = TextProvider("nvidia", "Sure! Here are the findings: ...")
    precise = TextProvider("gemini", '{"findings": []}')
    router = make_router(clock, routed(rambling, clock), routed(precise, clock), cache_entries=8)
    records: list[CallRecord] = []

    first = await router.complete(request(), on_call=records.append, validate=json_only)
    again = await router.complete(request(), on_call=records.append, validate=json_only)

    assert (first.provider, again.provider, again.cached) == ("gemini", "gemini", True)
    assert statuses(records) == [
        ("nvidia", CallStatus.REJECTED),
        ("gemini", CallStatus.OK),
        ("gemini", CallStatus.CACHED),
    ]
    assert records[0].detail == "nvidia: answer was not JSON"
    assert rambling.calls == 1
    assert router.status()[0].breaker.state is BreakerState.CLOSED


async def test_a_cached_answer_that_fails_validation_is_not_served(clock: FakeClock) -> None:
    plain = TextProvider("nvidia", "plain text")
    router = make_router(clock, routed(plain, clock), cache_entries=8)
    await router.complete(request())

    with pytest.raises(AllProvidersUnavailableError):
        await router.complete(request(), validate=json_only)

    assert plain.calls == 2
