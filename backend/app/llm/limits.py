"""Client-side rate limiting, so calls stay under provider limits instead of hitting 429s.

Each provider's requests per minute and per day are counted in sliding windows,
and its tokens per minute in a continuously refilling token bucket, all sized at
a safety fraction of the real limits. Before a call the router asks how long it
would have to wait; if that is too long it tries another provider instead.

Requests use windows rather than buckets because providers count requests in
windows. A bucket that starts full and refills while it is spent lets through up
to twice its capacity in the first window, which drew 429s from Gemini's free
tier of five requests a minute. Token limits are enforced far more loosely, so
the bucket's smoother accounting is kept for them.
"""

import bisect
import contextlib
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

    def reserve(self, amount: float) -> float:
        """Spend ``amount`` now, going into debt if necessary.

        Returns:
            The amount charged, which is capped at capacity like the wait.
        """
        self._refill()
        charged = min(amount, self._capacity)
        self._level -= charged
        return charged

    def refund(self, amount: float) -> None:
        """Return unused budget, up to capacity."""
        self._refill()
        self._level = min(self._capacity, self._level + amount)

    def _refill(self) -> None:
        now = self._clock.monotonic()
        elapsed = max(0.0, now - self._updated)
        self._level = min(self._capacity, self._level + elapsed * self._refill_per_second)
        self._updated = now


class SlidingWindow:
    """At most ``capacity`` requests in any ``window_seconds``.

    Each reservation books the earliest time it may be sent, which can lie in the
    future, so concurrent callers queue behind each other instead of overspending.
    """

    def __init__(self, capacity: float, window_seconds: float, clock: Clock) -> None:
        self._capacity = max(1, int(capacity))
        self._window = window_seconds
        self._clock = clock
        self._slots: list[float] = []

    def wait_time(self) -> float:
        """Seconds until one more request may be sent."""
        now = self._prune()
        return max(0.0, self._next_slot(now) - now)

    def reserve(self) -> float:
        """Book the earliest free slot.

        Returns:
            The slot's time, which identifies the booking for :meth:`cancel`.
        """
        now = self._prune()
        slot = self._next_slot(now)
        bisect.insort(self._slots, slot)
        return slot

    def cancel(self, slot: float) -> None:
        """Release a booking for a request that was never sent."""
        with contextlib.suppress(ValueError):
            self._slots.remove(slot)

    def _next_slot(self, now: float) -> float:
        if len(self._slots) < self._capacity:
            return now
        # The window ending at the new slot must not contain `capacity` earlier slots.
        return max(now, self._slots[-self._capacity] + self._window)

    def _prune(self) -> float:
        now = self._clock.monotonic()
        del self._slots[: bisect.bisect_right(self._slots, now - self._window)]
        return now


@dataclass(frozen=True)
class Reservation:
    """What one request took from a limiter, so it can be cancelled or settled exactly.

    Attributes:
        tokens: Tokens charged to the token bucket.
        slots: The booking in each request window, in the limiter's window order.
    """

    tokens: float
    slots: tuple[float, ...] = ()


@dataclass(frozen=True)
class RateLimits:
    """A provider's published limits. ``None`` means the provider does not enforce one."""

    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    requests_per_day: int | None = None
    safety: float = 0.8


class RateLimiter:
    """Combines a provider's request windows and token bucket."""

    def __init__(self, limits: RateLimits, clock: Clock) -> None:
        self._request_windows = [
            SlidingWindow(_scaled(limit, limits.safety), window, clock)
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
        """Seconds until one request of ``tokens`` fits every window and the token bucket."""
        waits = [window.wait_time() for window in self._request_windows]
        if self._token_bucket is not None:
            waits.append(self._token_bucket.wait_time(tokens))
        return max(waits, default=0.0)

    def reserve(self, tokens: int) -> Reservation:
        """Account for one request of an estimated ``tokens`` in every limit."""
        slots = tuple(window.reserve() for window in self._request_windows)
        charged = self._token_bucket.reserve(tokens) if self._token_bucket is not None else 0.0
        return Reservation(tokens=charged, slots=slots)

    def cancel(self, reservation: Reservation) -> None:
        """Return the request and its tokens, for a call that was never sent."""
        for window, slot in zip(self._request_windows, reservation.slots, strict=True):
            window.cancel(slot)
        if self._token_bucket is not None:
            self._token_bucket.refund(reservation.tokens)

    def settle(self, reservation: Reservation, used_tokens: int) -> None:
        """Correct the token budget to what a sent call actually used.

        Unused tokens are returned, and tokens beyond the estimate are charged, so
        the budget follows real usage even when the estimate was too low.
        """
        if self._token_bucket is None:
            return
        difference = reservation.tokens - used_tokens
        if difference > 0:
            self._token_bucket.refund(difference)
        elif difference < 0:
            self._token_bucket.reserve(-difference)


def _scaled(limit: int, safety: float) -> float:
    return max(1.0, limit * safety)
