"""Error taxonomy for the Alleo SDK (blueprint §4.2)."""

from __future__ import annotations

from typing import Any


class AlleoError(Exception):
    """Base class for every error this SDK raises."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        self.request_id = request_id


class AuthenticationError(AlleoError):
    """401 after the one allowed refresh-retry, or bad credentials."""


class AlleoPermissionError(AlleoError):
    """403. Exported as ``alleo.PermissionError`` for a friendlier name."""


class NotFoundError(AlleoError):
    """404."""


class ConflictError(AlleoError):
    """409 (e.g. duplicate email)."""


class ValidationError(AlleoError):
    """400 or 422."""


class RateLimitError(AlleoError):
    """429 after retries are exhausted."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        status_code: int | None = None,
        response_body: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            response_body=response_body,
            request_id=request_id,
        )
        self.retry_after = retry_after


class ServerError(AlleoError):
    """5xx after retries are exhausted."""


class NetworkError(AlleoError):
    """DNS / connect / read timeout."""
