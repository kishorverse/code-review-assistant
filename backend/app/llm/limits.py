"""Client-side rate limiting, so calls stay under provider limits instead of hitting 429s.

Each provider gets continuously refilling token buckets for requests per minute,
tokens per minute and requests per day, sized at a safety fraction of the real
limits. Before a call the router asks how long it would have to wait; if that is
too long it tries another provider instead of waiting.
"""

from dataclasses import dataclass

from app.llm.clock import Clock

MINUTE = 60.0
DAY = 86_400.0


class TokenBucket:
    """A budget of ``capacity`` units that refills evenly over ``window_seconds``.

    Reservations may push the level below zero; that debt is repaid by refill,
    so concurrent reservations never overspend the budget.
    """

    def __init__(self, capacity: float, window_seconds: float, clock: Clock) -> None:
        self._capacity = capacity
        self._refill_per_second = capacity / window_seconds
        self._clock = clock
        self._level = capacity
        self._updated = clock.monotonic()

    def wait_time(self, amount: float) -> float:
        """Seconds until ``amount`` can be spent. Amounts above capacity wait for a full bucket."""
        self._refill()
        needed = min(amount, self._capacity)
        if self._level >= needed:
            return 0.0
        return (needed - self._level) / self._refill_per_second

    def reserve(self, amount: float) -> None:
        """Spend ``amount`` now, going into debt if necessary."""
        self._refill()
        self._level -= min(amount, self._capacity)

    def refund(self, amount: float) -> None:
        """Return unused budget, up to capacity."""
        self._refill()
        self._level = min(self._capacity, self._level + amount)

    def _refill(self) -> None:
        now = self._clock.monotonic()
        elapsed = max(0.0, now - self._updated)
        self._level = min(self._capacity, self._level + elapsed * self._refill_per_second)
        self._updated = now


@dataclass(frozen=True)
class RateLimits:
    """A provider's published limits. ``None`` means the provider does not enforce one."""

    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    requests_per_day: int | None = None
    safety: float = 0.8


class RateLimiter:
    """Combines a provider's request, token and daily buckets."""

    def __init__(self, limits: RateLimits, clock: Clock) -> None:
        self._request_buckets = [
            TokenBucket(_scaled(limit, limits.safety), window, clock)
            for limit, window in (
                (limits.requests_per_minute, MINUTE),
                (limits.requests_per_day, DAY),
            )
            if limit is not None
        ]
        self._token_bucket = (
            TokenBucket(_scaled(limits.tokens_per_minute, limits.safety), MINUTE, clock)
            if limits.tokens_per_minute is not None
            else None
        )

    def wait_time(self, tokens: int) -> float:
        """Seconds until one request of ``tokens`` fits every bucket."""
        waits = [bucket.wait_time(1) for bucket in self._request_buckets]
        if self._token_bucket is not None:
            waits.append(self._token_bucket.wait_time(tokens))
        return max(waits, default=0.0)

    def reserve(self, tokens: int) -> None:
        """Account for one request of ``tokens`` in every bucket."""
        for bucket in self._request_buckets:
            bucket.reserve(1)
        if self._token_bucket is not None:
            self._token_bucket.reserve(tokens)

    def refund_tokens(self, tokens: int) -> None:
        """Give back tokens that were reserved but not used."""
        if self._token_bucket is not None and tokens > 0:
            self._token_bucket.refund(tokens)


def _scaled(limit: int, safety: float) -> float:
    return max(1.0, limit * safety)
