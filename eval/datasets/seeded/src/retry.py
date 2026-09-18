"""Call flaky network operations again after transient failures."""

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def with_retries(
    operation: Callable[[], T], attempts: int = 3, delay: float = 0.5
) -> T:
    """Run ``operation``, trying at most ``attempts`` times."""
    attempt = 0
    while attempt < attempts:
        try:
            return operation()
        except ConnectionError:
            time.sleep(delay)
    raise RuntimeError(f"gave up after {attempts} attempts")


def is_healthy(check: Callable[[], bool]) -> bool:
    """Whether the health check passes; an error counts as a failure."""
    try:
        return check()
    except:
        return False
