"""Time source for rate limiting and circuit breaking, replaceable in tests."""

import asyncio
import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Monotonic time for measuring intervals, wall time for provider reset times, and sleep."""

    def monotonic(self) -> float:
        """Seconds from an arbitrary start; never goes backwards."""
        ...

    def now(self) -> datetime:
        """The current time, timezone-aware."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Wait without blocking the event loop."""
        ...


class SystemClock:
    """The real clock."""

    def monotonic(self) -> float:
        """See :meth:`Clock.monotonic`."""
        return time.monotonic()

    def now(self) -> datetime:
        """See :meth:`Clock.now`."""
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        """See :meth:`Clock.sleep`."""
        await asyncio.sleep(seconds)
