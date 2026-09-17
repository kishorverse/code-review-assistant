from datetime import UTC, datetime, timedelta

import pytest


class FakeClock:
    """A clock that only moves when told to, or when something sleeps."""

    def __init__(self, start: datetime = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)) -> None:
        self._monotonic = 1_000.0
        self._now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self._monotonic

    def now(self) -> datetime:
        return self._now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
