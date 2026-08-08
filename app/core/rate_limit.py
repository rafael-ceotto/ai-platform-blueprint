"""In-process, fixed-window rate limiter.

See docs/adr/0003-api-key-auth-and-rate-limiting.md for why this is
hand-rolled and in-memory rather than a library or a Redis-backed limiter:
sufficient for a single-process MVP, with no extra infrastructure.

Single-process only: state lives in a plain dict, so limits are not
shared across multiple uvicorn workers or replicas. See the ADR's revisit
triggers for when to move to a shared (e.g. Redis) backend.
"""

import time
from collections.abc import Callable


class InMemoryRateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._time_fn = time_fn
        self._windows: dict[str, tuple[float, int]] = {}  # key -> (window_start, count)

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    def allow(self, key: str) -> bool:
        """Record a request for `key` and return whether it's within the limit."""
        now = self._time_fn()
        window_start, count = self._windows.get(key, (now, 0))

        if now - window_start >= self._window_seconds:
            window_start, count = now, 0

        count += 1
        self._windows[key] = (window_start, count)

        return count <= self._max_requests
