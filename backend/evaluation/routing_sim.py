"""Simulate a scan's model calls under rate limits: plain clients versus the router.

Nothing leaves the machine. Each provider is a simulated server that enforces
its own per-minute limit, answers after a fixed latency, and can be taken down.
A time-scaled clock makes a simulated minute pass in one real second, so limits
measured in minutes play out in seconds while calls still overlap as they
would for real. The router under test is Margin's own, with its real rate
limiter and circuit breakers; only the clock and the servers are simulated.

Strategies compared:

- ``naive``: every call goes to the preferred provider at once, and a 429 is
  retried after 1, 2 and 4 seconds before giving up. Typical of a first client.
- ``retry-after``: as naive, but waits as long as each 429 says, without limit.
  Completes eventually, at the cost of time and rejected calls.
- ``router``: Margin's router with the providers' limits configured.

The preferred provider answers in 3 simulated seconds, so with four calls in
flight it could take 80 a minute: its 40-a-minute limit, not its latency, sets
the pace, as it does for a fast hosted model.
"""

import asyncio
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.errors import (
    AllProvidersUnavailableError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.llm.breaker import CircuitBreaker
from app.llm.cache import ResponseCache
from app.llm.limits import RateLimiter, RateLimits
from app.llm.models import LLMRequest, LLMResponse, Priority, Task
from app.llm.router import RoutedProvider, Router

MINUTE = 60.0
NAIVE_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
CONCURRENCY = 6
"""Calls a scan keeps in flight, as ReviewOptions does by default."""


class ScaledClock:
    """A clock on which ``scale`` simulated seconds pass per real second."""

    def __init__(self, scale: float = 60.0) -> None:
        self._scale = scale
        self._origin = time.monotonic()
        self._epoch = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)

    def monotonic(self) -> float:
        """Simulated seconds since the clock was created."""
        return (time.monotonic() - self._origin) * self._scale

    def now(self) -> datetime:
        """Simulated wall time."""
        return self._epoch + timedelta(seconds=self.monotonic())

    async def sleep(self, seconds: float) -> None:
        """Wait ``seconds`` of simulated time."""
        await asyncio.sleep(max(0.0, seconds) / self._scale)


@dataclass
class SimulatedServer:
    """A provider's endpoint: a per-minute request limit and a fixed latency.

    Attributes:
        rejected: 429 responses sent.
        served: Calls answered.
    """

    name: str
    requests_per_minute: int
    latency_seconds: float
    clock: ScaledClock
    down: bool = False
    rejected: int = 0
    served: int = 0
    failed: int = 0
    _recent: deque[float] = field(default_factory=deque)

    async def handle(self) -> None:
        """Accept one call or raise the error the real provider would."""
        now = self.clock.monotonic()
        while self._recent and self._recent[0] <= now - MINUTE:
            self._recent.popleft()
        if self.down:
            self.failed += 1
            raise ProviderUnavailableError(self.name, "HTTP 503: overloaded")
        if len(self._recent) >= self.requests_per_minute:
            self.rejected += 1
            retry_after = MINUTE - (now - self._recent[0])
            raise RateLimitedError(self.name, "HTTP 429", retry_after=retry_after)
        self._recent.append(now)
        await self.clock.sleep(self.latency_seconds)
        self.served += 1


@dataclass
class SimulatedProvider:
    """An ``LLMProvider`` backed by a simulated server."""

    server: SimulatedServer
    external: bool = True
    model: str = "simulated"

    @property
    def name(self) -> str:
        """The server's name."""
        return self.server.name

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Answer after the server accepts the call."""
        await self.server.handle()
        return LLMResponse(text='{"findings": []}', provider=self.name, model=self.model)


@dataclass(frozen=True)
class ServerSpec:
    """A provider in a scenario; ``believed_rpm`` is what the router is told."""

    name: str
    requests_per_minute: int
    latency_seconds: float
    down: bool = False
    believed_rpm: int | None = None


@dataclass(frozen=True)
class Scenario:
    """A burst of review calls against a set of providers, preferred first."""

    name: str
    description: str
    requests: int
    servers: tuple[ServerSpec, ...]


@dataclass(frozen=True)
class Outcome:
    """What one strategy achieved in one scenario."""

    scenario: str
    strategy: str
    requests: int
    completed: int
    failed: int
    rejected_429: int
    served_by_fallback: int
    minutes: float


SCENARIOS = (
    Scenario(
        name="burst",
        description="120 review calls; NVIDIA-like 40 RPM preferred, Gemini-like 5 RPM "
        "and Hugging Face-like 30 RPM as fallbacks",
        requests=120,
        servers=(
            ServerSpec("primary", 40, 3.0),
            ServerSpec("secondary", 5, 10.0),
            ServerSpec("tertiary", 30, 6.0),
        ),
    ),
    Scenario(
        name="outage",
        description="as burst, but the preferred provider answers every call with 503",
        requests=120,
        servers=(
            ServerSpec("primary", 40, 3.0, down=True),
            ServerSpec("secondary", 5, 10.0),
            ServerSpec("tertiary", 30, 6.0),
        ),
    ),
    Scenario(
        name="wrong-limits",
        description="as burst, but the router believes the preferred provider allows "
        "60 RPM when it allows 40",
        requests=120,
        servers=(
            ServerSpec("primary", 40, 3.0, believed_rpm=60),
            ServerSpec("secondary", 5, 10.0),
            ServerSpec("tertiary", 30, 6.0),
        ),
    ),
)


def _request(index: int) -> LLMRequest:
    # Distinct prompts, so the response cache cannot answer any of them.
    return LLMRequest(
        task=Task.REVIEW,
        system="Review the code.",
        user=f"chunk {index}",
        max_output_tokens=512,
        priority=Priority.BATCH,
        allow_external=True,
    )


def _servers(scenario: Scenario, clock: ScaledClock) -> list[SimulatedServer]:
    return [
        SimulatedServer(spec.name, spec.requests_per_minute, spec.latency_seconds, clock, spec.down)
        for spec in scenario.servers
    ]


async def run_plain(scenario: Scenario, *, honour_retry_after: bool) -> Outcome:
    """Call the preferred provider directly, retrying 429s as a simple client would."""
    clock = ScaledClock()
    servers = _servers(scenario, clock)
    preferred = servers[0]
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one() -> bool:
        async with semaphore:
            attempt = 0
            while True:
                try:
                    await preferred.handle()
                    return True
                except RateLimitedError as error:
                    if honour_retry_after:
                        await clock.sleep(error.retry_after or 1.0)
                        continue
                    if attempt == len(NAIVE_BACKOFF_SECONDS):
                        return False
                    await clock.sleep(NAIVE_BACKOFF_SECONDS[attempt])
                    attempt += 1
                except ProviderError:
                    if attempt == len(NAIVE_BACKOFF_SECONDS):
                        return False
                    await clock.sleep(NAIVE_BACKOFF_SECONDS[attempt])
                    attempt += 1

    results = await asyncio.gather(*(one() for _ in range(scenario.requests)))
    return _outcome(
        scenario,
        "retry-after" if honour_retry_after else "naive",
        results,
        servers,
        0,
        clock,
    )


async def run_router(scenario: Scenario) -> Outcome:
    """Send every call through Margin's router."""
    clock = ScaledClock()
    servers = _servers(scenario, clock)
    routed = [
        RoutedProvider(
            provider=SimulatedProvider(server),
            limiter=RateLimiter(
                RateLimits(requests_per_minute=spec.believed_rpm or spec.requests_per_minute),
                clock,
            ),
            breaker=CircuitBreaker(clock, probe_timeout_seconds=60),
            semaphore=asyncio.Semaphore(4),
            timeout_seconds=60,
        )
        for spec, server in zip(scenario.servers, servers, strict=True)
    ]
    router = Router(
        routed,
        {Task.REVIEW: [server.name for server in servers]},
        clock=clock,
        cache=ResponseCache(),
        max_wait_seconds={Priority.INTERACTIVE: 5.0, Priority.BATCH: 30.0},
    )
    semaphore = asyncio.Semaphore(CONCURRENCY)
    preferred = servers[0].name
    fallbacks = 0

    async def one(index: int) -> bool:
        nonlocal fallbacks
        async with semaphore:
            try:
                response = await router.complete(_request(index))
            except AllProvidersUnavailableError:
                return False
            fallbacks += response.provider != preferred
            return True

    results = await asyncio.gather(*(one(i) for i in range(scenario.requests)))
    return _outcome(scenario, "router", results, servers, fallbacks, clock)


def _outcome(
    scenario: Scenario,
    strategy: str,
    results: Sequence[bool],
    servers: Sequence[SimulatedServer],
    fallbacks: int,
    clock: ScaledClock,
) -> Outcome:
    return Outcome(
        scenario=scenario.name,
        strategy=strategy,
        requests=len(results),
        completed=sum(results),
        failed=len(results) - sum(results),
        rejected_429=sum(server.rejected for server in servers),
        served_by_fallback=fallbacks,
        minutes=round(clock.monotonic() / MINUTE, 1),
    )


async def simulate(scenarios: Sequence[Scenario] = SCENARIOS) -> list[Outcome]:
    """Every strategy in every scenario, one after another."""
    outcomes = []
    for scenario in scenarios:
        outcomes.append(await run_plain(scenario, honour_retry_after=False))
        outcomes.append(await run_plain(scenario, honour_retry_after=True))
        outcomes.append(await run_router(scenario))
    return outcomes


def to_markdown(outcomes: Sequence[Outcome]) -> str:
    """The routing table quoted in ``docs/evaluation.md``."""
    rows = [
        "| Scenario | Strategy | Completed | Failed | 429s received | Served by fallback "
        "| Simulated minutes |",
        "|---|---|---|---|---|---|---|",
    ]
    rows += [
        f"| {o.scenario} | {o.strategy} | {o.completed}/{o.requests} | {o.failed} "
        f"| {o.rejected_429} | {o.served_by_fallback} | {o.minutes} |"
        for o in outcomes
    ]
    notes = [f"- **{s.name}**: {s.description}." for s in SCENARIOS]
    return "\n".join(rows) + "\n\n" + "\n".join(notes) + "\n"
