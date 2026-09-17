from datetime import timedelta

import pytest

from app.llm.breaker import BreakerState, CircuitBreaker
from tests.llm.conftest import FakeClock


def test_opens_after_repeated_failures_and_probes_after_cooldown(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock, failure_threshold=3, cooldown_seconds=30)
    for _ in range(2):
        breaker.record_failure("HTTP 503")
    assert breaker.allows()

    breaker.record_failure("HTTP 503")
    assert breaker.state is BreakerState.OPEN
    assert not breaker.allows()

    clock.advance(30)
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.allows()
    assert not breaker.allows(), "only one probe at a time"


def test_successful_probe_closes_and_failed_probe_reopens(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock, failure_threshold=1, cooldown_seconds=10)
    breaker.record_failure("timeout")
    clock.advance(10)

    assert breaker.allows()
    breaker.record_failure("timeout")
    assert breaker.state is BreakerState.OPEN

    clock.advance(10)
    assert breaker.allows()
    breaker.record_success()
    assert breaker.state is BreakerState.CLOSED
    assert breaker.status().reason is None


def test_probe_that_never_reports_back_does_not_block_forever(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock, failure_threshold=1, cooldown_seconds=10)
    breaker.record_failure("timeout")
    clock.advance(10)
    assert breaker.allows()

    clock.advance(10)
    assert breaker.allows()


def test_rate_limit_honours_retry_after(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock)

    breaker.record_rate_limit(retry_after=12)

    assert breaker.status().reopens_in_seconds == pytest.approx(12)
    assert breaker.status().reason == "rate limited"
    clock.advance(12)
    assert breaker.allows()


def test_rate_limit_without_retry_after_backs_off_exponentially_up_to_a_cap(
    clock: FakeClock,
) -> None:
    breaker = CircuitBreaker(clock, max_backoff_seconds=60)
    delays = []
    for _ in range(7):
        breaker.record_rate_limit(retry_after=None)
        delays.append(breaker.status().reopens_in_seconds)

    assert delays == [2, 4, 8, 16, 32, 60, 60]


def test_open_until_a_quota_reset_time(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock, cooldown_seconds=30)

    breaker.open_until(clock.now() + timedelta(hours=5), "daily quota used")

    assert breaker.status().reopens_in_seconds == pytest.approx(5 * 3600)
    assert breaker.status().reason == "daily quota used"
    clock.advance(5 * 3600 - 1)
    assert not breaker.allows()
