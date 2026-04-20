import httpx
import pytest

from alleo._core import _Core


def make_core(max_retries=3):
    return _Core(
        base_url="https://x",
        access_key="ak",
        secret_key="sk",
        timeout=30.0,
        max_retries=max_retries,
        user_agent="alleo-sdk-python/0.1.1",
        logger=None,
    )


@pytest.mark.parametrize("attempt,expected", [(0, 0.5), (1, 1.0), (2, 2.0)])
def test_retry_5xx_uses_exponential(attempt, expected):
    core = make_core()
    resp = httpx.Response(500)
    assert core.should_retry(attempt, resp) == expected


def test_retry_5xx_exhausted_returns_none():
    core = make_core(max_retries=3)
    resp = httpx.Response(500)
    assert core.should_retry(3, resp) is None


def test_retry_429_uses_retry_after_header():
    core = make_core()
    resp = httpx.Response(429, headers={"Retry-After": "7"})
    assert core.should_retry(0, resp) == 7.0


def test_retry_429_without_header_falls_back_to_exponential():
    core = make_core()
    resp = httpx.Response(429)
    assert core.should_retry(0, resp) == 0.5


def test_retry_429_exhausted_returns_none():
    core = make_core(max_retries=3)
    assert core.should_retry(3, httpx.Response(429, headers={"Retry-After": "1"})) is None


def test_no_retry_on_4xx_except_429():
    core = make_core()
    for status in (400, 401, 403, 404, 409, 422):
        assert core.should_retry(0, httpx.Response(status)) is None, status


def test_no_retry_on_2xx():
    core = make_core()
    assert core.should_retry(0, httpx.Response(200)) is None


@pytest.mark.parametrize("attempt,expected", [(0, 0.5), (1, 1.0), (2, 2.0)])
def test_retry_network_error_uses_exponential(attempt, expected):
    core = make_core()
    assert core.should_retry(attempt, None, network_error=True) == expected


def test_retry_network_error_exhausted():
    core = make_core(max_retries=3)
    assert core.should_retry(3, None, network_error=True) is None


def test_retry_max_retries_above_schedule_clamps_backoff():
    core = make_core(max_retries=5)
    assert core.should_retry(3, httpx.Response(500)) == 2.0
    assert core.should_retry(4, httpx.Response(500)) == 2.0
    assert core.should_retry(5, httpx.Response(500)) is None
