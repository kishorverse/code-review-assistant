"""Per-provider circuit breaker.

After repeated failures, a rate-limit response or an exhausted quota, the
breaker opens and the router stops sending that provider traffic. When the
open period ends, a single probe request is let through: success closes the
breaker, failure opens it again.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.llm.clock import Clock

FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 60.0


class BreakerState(StrEnum):
    """Whether a provider receives traffic."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class BreakerStatus:
    """A snapshot for the providers page and logs."""

    state: BreakerState
    reopens_in_seconds: float
    reason: str | None


class CircuitBreaker:
    """Tracks one provider's health."""

    def __init__(
        self,
        clock: Clock,
        failure_threshold: int = FAILURE_THRESHOLD,
        cooldown_seconds: float = COOLDOWN_SECONDS,
        max_backoff_seconds: float = MAX_BACKOFF_SECONDS,
    ) -> None:
        self._clock = clock
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._failures = 0
        self._rate_limits = 0
        self._open_until: float | None = None
        self._probe_until: float | None = None
        self._reason: str | None = None

    @property
    def state(self) -> BreakerState:
        """The current state, accounting for elapsed time."""
        now = self._clock.monotonic()
        if self._open_until is not None and now < self._open_until:
            return BreakerState.OPEN
        if self._open_until is not None:
            return BreakerState.HALF_OPEN
        return BreakerState.CLOSED

    def allows(self) -> bool:
        """Whether a call may be made now.

        In the half-open state only one probe is allowed per cooldown period, so
        a probe that never reports back (for example a cancelled call) cannot
        block the provider forever.
        """
        state = self.state
        if state is BreakerState.CLOSED:
            return True
        if state is BreakerState.OPEN:
            return False
        now = self._clock.monotonic()
        if self._probe_until is not None and now < self._probe_until:
            return False
        self._probe_until = now + self._cooldown_seconds
        return True

    def record_success(self) -> None:
        """Close the breaker and forget past failures."""
        self._failures = 0
        self._rate_limits = 0
        self._open_until = None
        self._probe_until = None
        self._reason = None

    def record_failure(self, reason: str) -> None:
        """Count a transient failure; open after too many, or at once if probing."""
        self._failures += 1
        if self.state is BreakerState.HALF_OPEN or self._failures >= self._failure_threshold:
            self._open_for(self._cooldown_seconds, reason)

    def record_rate_limit(self, retry_after: float | None) -> None:
        """Open for the provider's requested delay, or back off exponentially without one."""
        self._rate_limits += 1
        if retry_after is not None:
            delay = retry_after
        else:
            delay = min(2.0**self._rate_limits, self._max_backoff_seconds)
        self._open_for(delay, "rate limited")

    def open_until(self, moment: datetime, reason: str) -> None:
        """Stay open until a wall-clock time, such as a daily quota reset."""
        seconds = (moment - self._clock.now()).total_seconds()
        self._open_for(max(seconds, self._cooldown_seconds), reason)

    def open_for(self, seconds: float, reason: str) -> None:
        """Stay open for a fixed period."""
        self._open_for(seconds, reason)

    def status(self) -> BreakerStatus:
        """A snapshot of the state, time until the next probe and why it opened."""
        now = self._clock.monotonic()
        remaining = max(0.0, (self._open_until or now) - now)
        return BreakerStatus(state=self.state, reopens_in_seconds=remaining, reason=self._reason)

    def _open_for(self, seconds: float, reason: str) -> None:
        self._open_until = self._clock.monotonic() + seconds
        self._probe_until = None
        self._reason = reason
