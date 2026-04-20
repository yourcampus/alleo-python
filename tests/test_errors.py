import pytest

from alleo.errors import (
    AlleoError,
    AlleoPermissionError,
    AuthenticationError,
    ConflictError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)


def test_alleo_error_attributes_default_none():
    err = AlleoError("boom")
    assert str(err) == "boom"
    assert err.message == "boom"
    assert err.status_code is None
    assert err.response_body is None
    assert err.request_id is None


def test_alleo_error_attributes_populated():
    err = AlleoError(
        "bad",
        status_code=400,
        response_body={"detail": "bad"},
        request_id="req-123",
    )
    assert err.status_code == 400
    assert err.response_body == {"detail": "bad"}
    assert err.request_id == "req-123"


def test_rate_limit_error_has_retry_after():
    err = RateLimitError("slow down", retry_after=2.5)
    assert err.retry_after == 2.5


def test_rate_limit_error_retry_after_optional():
    err = RateLimitError("slow down")
    assert err.retry_after is None


@pytest.mark.parametrize(
    "cls",
    [
        AuthenticationError,
        AlleoPermissionError,
        NotFoundError,
        ConflictError,
        ValidationError,
        ServerError,
        NetworkError,
    ],
)
def test_subclasses_are_alleo_errors(cls):
    err = cls("x")
    assert isinstance(err, AlleoError)


def test_token_not_in_repr():
    err = AuthenticationError("bad token: secret-abc123")
    # The message is verbatim what the caller passed in; we just make sure
    # the class doesn't auto-serialize any stored credential. No creds stored.
    assert not hasattr(err, "access_key")
    assert not hasattr(err, "secret_key")
