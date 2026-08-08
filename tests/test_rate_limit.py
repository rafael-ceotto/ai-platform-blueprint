"""Tests for the in-memory rate limiter."""

from app.core.rate_limit import InMemoryRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_allows_requests_up_to_the_limit() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60, time_fn=clock)

    assert limiter.allow("key-a") is True
    assert limiter.allow("key-a") is True
    assert limiter.allow("key-a") is True


def test_rejects_requests_over_the_limit() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60, time_fn=clock)

    assert limiter.allow("key-a") is True
    assert limiter.allow("key-a") is True
    assert limiter.allow("key-a") is False


def test_resets_after_the_window_elapses() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, time_fn=clock)

    assert limiter.allow("key-a") is True
    assert limiter.allow("key-a") is False

    clock.advance(61)

    assert limiter.allow("key-a") is True


def test_limits_are_independent_per_key() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, time_fn=clock)

    assert limiter.allow("key-a") is True
    assert limiter.allow("key-b") is True
    assert limiter.allow("key-a") is False
    assert limiter.allow("key-b") is False
