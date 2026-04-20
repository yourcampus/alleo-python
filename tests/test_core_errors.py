import httpx
import pytest

from alleo._core import _Core
from alleo.errors import (
    AlleoError,
    AlleoPermissionError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)


def make_core():
    return _Core(
        base_url="https://x",
        access_key="ak",
        secret_key="sk",
        timeout=30.0,
        max_retries=3,
        user_agent="alleo-sdk-python/0.1.1",
        logger=None,
    )


def _resp(status: int, body: dict | list | None = None) -> httpx.Response:
    if body is None:
        return httpx.Response(status)
    return httpx.Response(status, json=body)


@pytest.mark.parametrize(
    "status,body,cls,msg_contains",
    [
        (400, {"detail": "bad input"}, ValidationError, "bad input"),
        (401, {"detail": "invalid_client"}, AuthenticationError, "invalid_client"),
        (403, {"detail": "nope"}, AlleoPermissionError, "nope"),
        (404, {"detail": "missing"}, NotFoundError, "missing"),
        (409, {"detail": "dup email"}, ConflictError, "dup email"),
        (500, {"detail": "boom"}, ServerError, "boom"),
        (502, None, ServerError, "502"),
    ],
)
def test_map_error_status_to_class(status, body, cls, msg_contains):
    core = make_core()
    resp = _resp(status, body)
    err = core.map_error(resp)
    assert isinstance(err, cls)
    assert msg_contains in err.message
    assert err.status_code == status
    if body is not None:
        assert err.response_body == body


def test_map_error_422_flattens_detail_list():
    core = make_core()
    body = {
        "detail": [
            {
                "loc": ["body", "email"],
                "msg": "value is not a valid email",
                "type": "value_error.email",
            },
            {
                "loc": ["body", "first_name"],
                "msg": "field required",
                "type": "value_error.missing",
            },
        ]
    }
    err = core.map_error(_resp(422, body))
    assert isinstance(err, ValidationError)
    assert "body.email: value is not a valid email" in err.message
    assert "body.first_name: field required" in err.message


def test_map_error_422_fallback_when_body_unexpected():
    core = make_core()
    err = core.map_error(_resp(422, {"detail": "oddly a string"}))
    assert isinstance(err, ValidationError)
    assert "oddly a string" in err.message


def test_map_error_no_body():
    core = make_core()
    err = core.map_error(_resp(500, None))
    assert isinstance(err, ServerError)
    assert err.response_body is None


def test_map_error_non_json_body():
    core = make_core()
    resp = httpx.Response(500, content=b"<html>nope</html>")
    err = core.map_error(resp)
    assert isinstance(err, ServerError)
    assert err.response_body is None


def test_map_error_429_with_retry_after():
    core = make_core()
    resp = httpx.Response(429, headers={"Retry-After": "7"}, json={"detail": "slow down"})
    err = core.map_error(resp)
    assert isinstance(err, RateLimitError)
    assert err.retry_after == 7.0
    assert err.status_code == 429
    assert "slow down" in err.message


def test_map_error_429_without_retry_after():
    core = make_core()
    resp = httpx.Response(429, json={"detail": "slow"})
    err = core.map_error(resp)
    assert isinstance(err, RateLimitError)
    assert err.retry_after is None


def test_map_error_unknown_status_falls_back_to_alleo_error():
    core = make_core()
    err = core.map_error(httpx.Response(418, json={"detail": "teapot"}))
    assert type(err) is AlleoError
    assert err.status_code == 418
    assert "teapot" in err.message
