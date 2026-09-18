import pytest

from app.llm.limits import RateLimiter, RateLimits, SlidingWindow, TokenBucket
from tests.llm.conftest import FakeClock


def test_bucket_refills_evenly_over_its_window(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=10, window_seconds=60, clock=clock)
    for _ in range(10):
        bucket.reserve(1)

    assert bucket.wait_time(1) == pytest.approx(6.0)
    clock.advance(6)
    assert bucket.wait_time(1) == 0.0


def test_reservations_can_go_into_debt_that_refill_repays(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=10, window_seconds=10, clock=clock)
    bucket.reserve(10)
    bucket.reserve(5)

    assert bucket.wait_time(1) == pytest.approx(6.0)


def test_amounts_above_capacity_wait_for_a_full_bucket_instead_of_forever(
    clock: FakeClock,
) -> None:
    bucket = TokenBucket(capacity=100, window_seconds=60, clock=clock)
    bucket.reserve(100)

    assert bucket.wait_time(10_000) == pytest.approx(60.0)


def test_refund_never_exceeds_capacity(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=10, window_seconds=60, clock=clock)
    bucket.reserve(4)
    bucket.refund(100)

    assert bucket.wait_time(10) == 0.0


def test_limiter_applies_the_safety_margin_to_every_limit(clock: FakeClock) -> None:
    limiter = RateLimiter(
        RateLimits(requests_per_minute=10, tokens_per_minute=1000, safety=0.8), clock
    )
    for _ in range(8):
        assert limiter.wait_time(10) == 0.0
        limiter.reserve(10)

    assert limiter.wait_time(10) > 0.0


def test_limiter_waits_for_the_tightest_bucket(clock: FakeClock) -> None:
    limiter = RateLimiter(
        RateLimits(requests_per_minute=100, tokens_per_minute=1000, safety=1.0), clock
    )
    limiter.reserve(1000)

    assert limiter.wait_time(500) == pytest.approx(30.0)


def test_daily_limit_is_enforced(clock: FakeClock) -> None:
    limiter = RateLimiter(RateLimits(requests_per_day=10, safety=1.0), clock)
    for _ in range(10):
        limiter.reserve(1)

    assert limiter.wait_time(1) == pytest.approx(86_400.0)


def test_no_window_ever_holds_more_than_the_limit(clock: FakeClock) -> None:
    # A full bucket refilling while spent would let 8 through in the first minute.
    window = SlidingWindow(capacity=4, window_seconds=60, clock=clock)

    slots = [window.reserve() for _ in range(10)]

    assert slots == [1000.0] * 4 + [1060.0] * 4 + [1120.0] * 2
    assert all(sum(start - 60 < other <= start for other in slots) <= 4 for start in slots)


def test_a_full_window_waits_for_its_oldest_request_to_leave(clock: FakeClock) -> None:
    window = SlidingWindow(capacity=2, window_seconds=60, clock=clock)
    window.reserve()
    clock.advance(10)
    window.reserve()
    clock.advance(20)

    assert window.wait_time() == pytest.approx(30.0)
    clock.advance(30)
    assert window.wait_time() == 0.0


def test_a_cancelled_booking_frees_its_slot(clock: FakeClock) -> None:
    window = SlidingWindow(capacity=1, window_seconds=60, clock=clock)
    slot = window.reserve()

    window.cancel(slot)

    assert window.wait_time() == 0.0


def test_settle_returns_unused_tokens(clock: FakeClock) -> None:
    limiter = RateLimiter(RateLimits(tokens_per_minute=1000, safety=1.0), clock)
    reservation = limiter.reserve(800)

    limiter.settle(reservation, used_tokens=300)

    assert limiter.wait_time(700) == 0.0
    assert limiter.wait_time(701) > 0.0


def test_settle_charges_usage_beyond_the_estimate(clock: FakeClock) -> None:
    limiter = RateLimiter(RateLimits(tokens_per_minute=1000, safety=1.0), clock)
    reservation = limiter.reserve(200)

    limiter.settle(reservation, used_tokens=900)

    assert limiter.wait_time(100) == 0.0
    assert limiter.wait_time(101) > 0.0


def test_settle_never_refunds_more_than_was_charged(clock: FakeClock) -> None:
    limiter = RateLimiter(RateLimits(tokens_per_minute=1000, safety=1.0), clock)
    oversized = limiter.reserve(5000)
    other = limiter.reserve(500)

    limiter.settle(oversized, used_tokens=100)

    assert oversized.tokens == 1000
    assert other.tokens == 500
    assert limiter.wait_time(400) == 0.0
    assert limiter.wait_time(401) > 0.0


def test_cancel_returns_the_request_and_its_tokens(clock: FakeClock) -> None:
    limiter = RateLimiter(
        RateLimits(requests_per_minute=2, requests_per_day=2, tokens_per_minute=100, safety=1.0),
        clock,
    )
    limiter.reserve(10)
    cancelled = limiter.reserve(90)

    limiter.cancel(cancelled)

    assert limiter.wait_time(90) == 0.0


def test_unlimited_provider_never_waits(clock: FakeClock) -> None:
    limiter = RateLimiter(RateLimits(), clock)
    for _ in range(1000):
        limiter.reserve(10_000)

    assert limiter.wait_time(10_000) == 0.0
