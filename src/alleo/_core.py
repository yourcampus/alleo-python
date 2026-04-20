"""Transport-agnostic core: request building, error mapping, retry policy.

Sync and async clients share this. The only I/O primitives ``_Core`` knows
about are ``httpx.Request`` and ``httpx.Response`` objects.
"""

from __future__ import annotations

import json as jsonlib
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode

import httpx

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
from alleo.models import RateLimit

DEFAULT_BASE_URL = "https://api.yourcampus.co/customer_api/v1"


class _Core:
    def __init__(
        self,
        *,
        base_url: str,
        access_key: str,
        secret_key: str,
        timeout: float,
        max_retries: int,
        user_agent: str,
        logger: Callable[[str], None] | None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self.logger = logger
        self.clock = clock

    # ----- request building -----

    def build_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        form: Mapping[str, str] | None = None,
    ) -> httpx.Request:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers: dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        content: bytes | None = None
        query = None
        if params:
            query = {k: v for k, v in params.items() if v is not None}
        if json is not None:
            headers["Content-Type"] = "application/json"
            content = jsonlib.dumps(json).encode("utf-8")
        elif form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            content = urlencode(form).encode("utf-8")
        return httpx.Request(
            method=method,
            url=url,
            params=query,
            headers=headers,
            content=content,
        )

    # ----- rate-limit parsing -----

    def parse_rate_limit(self, resp: httpx.Response) -> RateLimit:
        return RateLimit(
            limit=_int_or_none(resp.headers.get("X-RateLimit-Limit")),
            remaining=_int_or_none(resp.headers.get("X-RateLimit-Remaining")),
            reset_seconds=_int_or_none(resp.headers.get("X-RateLimit-Reset")),
        )

    # ----- error mapping -----

    def map_error(self, resp: httpx.Response) -> AlleoError:
        body = _parse_json_body(resp)
        message = _extract_message(resp, body)
        status = resp.status_code
        kwargs: dict[str, Any] = {
            "status_code": status,
            "response_body": body,
            "request_id": resp.headers.get("X-Request-ID"),
        }
        if status == 400:
            return ValidationError(message, **kwargs)
        if status == 401:
            return AuthenticationError(message, **kwargs)
        if status == 403:
            return AlleoPermissionError(message, **kwargs)
        if status == 404:
            return NotFoundError(message, **kwargs)
        if status == 409:
            return ConflictError(message, **kwargs)
        if status == 422:
            return ValidationError(message, **kwargs)
        if status == 429:
            retry_after = _float_or_none(resp.headers.get("Retry-After"))
            return RateLimitError(message, retry_after=retry_after, **kwargs)
        if 500 <= status < 600:
            return ServerError(message, **kwargs)
        return AlleoError(message, **kwargs)

    # ----- retry policy -----

    _BACKOFF_SCHEDULE: tuple[float, ...] = (0.5, 1.0, 2.0)

    def should_retry(
        self,
        attempt: int,
        resp: httpx.Response | None,
        *,
        network_error: bool = False,
    ) -> float | None:
        """Return seconds to sleep before the next attempt, or None to raise.

        ``attempt`` is the 0-indexed number of attempts already made — so on
        the very first failure it is ``0`` and we sleep ``_BACKOFF_SCHEDULE[0]``.
        """
        if attempt >= self.max_retries:
            return None
        backoff = self._BACKOFF_SCHEDULE[min(attempt, len(self._BACKOFF_SCHEDULE) - 1)]
        if network_error:
            return backoff
        assert resp is not None
        if resp.status_code == 429:
            retry_after = _float_or_none(resp.headers.get("Retry-After"))
            if retry_after is not None:
                return retry_after
            return backoff
        if 500 <= resp.status_code < 600:
            return backoff
        return None


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_json_body(resp: httpx.Response) -> Any | None:
    ctype = resp.headers.get("Content-Type", "")
    if "application/json" not in ctype:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _extract_message(resp: httpx.Response, body: Any | None) -> str:
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            parts: list[str] = []
            for item in detail:
                if not isinstance(item, dict):
                    continue
                loc = item.get("loc") or []
                loc_str = ".".join(str(x) for x in loc)
                msg = str(item.get("msg", ""))
                parts.append(f"{loc_str}: {msg}" if loc_str else msg)
            if parts:
                return "; ".join(parts)
    # Fallback: use status + reason.
    return f"HTTP {resp.status_code}"
