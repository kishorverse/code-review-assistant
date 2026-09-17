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


def test_a_shorter_pause_never_replaces_a_longer_one(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock, failure_threshold=1)
    breaker.open_until(clock.now() + timedelta(hours=16), "quota used up")

    breaker.record_rate_limit(retry_after=5)
    breaker.record_failure("HTTP 503")

    assert breaker.status().reopens_in_seconds == pytest.approx(16 * 3600)
    assert breaker.status().reason == "quota used up"


def test_a_failed_probe_still_reopens_after_a_long_pause_ends(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock, cooldown_seconds=30)
    breaker.open_for(3600, "API key rejected")
    clock.advance(3600)
    assert breaker.allows()

    breaker.record_rate_limit(retry_after=5)

    assert breaker.state is BreakerState.OPEN
    assert breaker.status().reopens_in_seconds == pytest.approx(5)


def test_a_late_success_does_not_end_a_pause(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock)
    breaker.open_until(clock.now() + timedelta(hours=10), "quota used up")

    breaker.record_success()

    assert breaker.state is BreakerState.OPEN
    assert breaker.status().reason == "quota used up"


def test_probe_slot_lasts_for_the_probe_timeout(clock: FakeClock) -> None:
    breaker = CircuitBreaker(
        clock, failure_threshold=1, cooldown_seconds=10, probe_timeout_seconds=300
    )
    breaker.record_failure("timeout")
    clock.advance(10)
    assert breaker.allows()

    clock.advance(299)
    assert not breaker.allows()
    clock.advance(1)
    assert breaker.allows()


def test_a_rejected_probe_frees_the_probe_slot(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock, failure_threshold=1, cooldown_seconds=10)
    breaker.record_failure("timeout")
    clock.advance(10)
    assert breaker.allows()

    breaker.record_rejection()

    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.allows()


def test_backoff_survives_a_very_long_run_of_rate_limits(clock: FakeClock) -> None:
    breaker = CircuitBreaker(clock, max_backoff_seconds=60)

    for _ in range(2000):
        breaker.record_rate_limit(retry_after=None)

    assert breaker.status().reopens_in_seconds == pytest.approx(60)
