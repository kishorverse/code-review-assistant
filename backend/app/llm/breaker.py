"""Per-provider circuit breaker.

After repeated failures, a rate-limit response or an exhausted quota, the
breaker opens and the router stops sending that provider traffic. When the
open period ends, a single probe request is let through: success closes the
breaker, failure opens it again.

Calls run concurrently, so outcomes can arrive out of order. A pause is never
shortened by a later, shorter pause, and a success from a call that started
before the pause does not end it.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.llm.clock import Clock

FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 60.0
_MAX_BACKOFF_EXPONENT = 30


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
        probe_timeout_seconds: float | None = None,
    ) -> None:
        self._clock = clock
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._probe_timeout_seconds = (
            cooldown_seconds if probe_timeout_seconds is None else probe_timeout_seconds
        )
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
        """Whether a call may be made now. Ask immediately before calling.

        In the half-open state one probe is allowed. Another is handed out only
        after ``probe_timeout_seconds``, which should cover one call, so a probe
        that never reports back (for example a cancelled call) cannot block the
        provider forever.
        """
        state = self.state
        if state is BreakerState.CLOSED:
            return True
        if state is BreakerState.OPEN:
            return False
        now = self._clock.monotonic()
        if self._probe_until is not None and now < self._probe_until:
            return False
        self._probe_until = now + self._probe_timeout_seconds
        return True

    def record_success(self) -> None:
        """Close the breaker and forget past failures, unless a pause is in force.

        While the breaker is open, a success can only come from a call that
        started before the pause, so the failure that caused the pause is newer.
        """
        if self.state is BreakerState.OPEN:
            return
        self._failures = 0
        self._rate_limits = 0
        self._open_until = None
        self._probe_until = None
        self._reason = None

    def record_rejection(self) -> None:
        """The provider answered but refused this one request, so it is reachable.

        Health is unchanged, but a probe that ends this way frees the probe slot.
        """
        self._probe_until = None

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
            exponent = min(self._rate_limits, _MAX_BACKOFF_EXPONENT)
            delay = min(2.0**exponent, self._max_backoff_seconds)
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
        until = self._clock.monotonic() + seconds
        if self._open_until is not None and self._open_until >= until:
            return  # A longer pause, such as a daily quota, is already in force.
        self._open_until = until
        self._probe_until = None
        self._reason = reason
