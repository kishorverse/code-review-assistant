"""Count requests per client over a sliding time window."""

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """At most ``limit`` requests per client in any ``window`` seconds."""

    def __init__(self, limit: int, window: float) -> None:
        if limit < 1 or window <= 0:
            raise ValueError("limit and window must be positive")
        self.limit = limit
        self.window = window
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, client: str, now: float | None = None) -> bool:
        """Record a request from ``client`` if it is within the limit."""
        now = time.monotonic() if now is None else now
        recent = self._requests[client]
        while recent and recent[0] <= now - self.window:
            recent.popleft()
        if len(recent) >= self.limit:
            return False
        recent.append(now)
        return True

    def forget_idle(self, now: float | None = None) -> None:
        """Drop clients with no request inside the window, to bound memory."""
        now = time.monotonic() if now is None else now
        idle = [
            client
            for client, times in self._requests.items()
            if not times or times[-1] <= now - self.window
        ]
        for client in idle:
            del self._requests[client]
