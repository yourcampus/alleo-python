"""Token caches. HTTP I/O is injected via a ``fetch`` callable to keep this
module transport-agnostic.

The token fetch response is the raw decoded JSON body from ``POST
/oauth/token``: ``{"access_token": str, "token_type": "Bearer",
"expires_in": int}``.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

_REFRESH_MARGIN_SECONDS = 60.0


@dataclass
class _TokenState:
    access_token: str | None = None
    expires_at: float = 0.0  # monotonic seconds


def _apply(state: _TokenState, body: dict[str, Any], now: float) -> None:
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("token endpoint returned no access_token")
    expires_in = float(body.get("expires_in", 0))
    if expires_in <= 0:
        raise ValueError("token endpoint returned invalid expires_in")
    state.access_token = token
    state.expires_at = now + expires_in


def _needs_refresh(state: _TokenState, now: float) -> bool:
    if state.access_token is None:
        return True
    return now >= state.expires_at - _REFRESH_MARGIN_SECONDS


class SyncTokenCache:
    def __init__(
        self,
        *,
        fetch: Callable[[], dict[str, Any]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._state = _TokenState()
        self._lock = threading.Lock()

    def token(self) -> str:
        with self._lock:
            now = self._clock()
            if _needs_refresh(self._state, now):
                body = self._fetch()
                _apply(self._state, body, self._clock())
            assert self._state.access_token is not None
            return self._state.access_token

    def invalidate(self) -> None:
        with self._lock:
            self._state.access_token = None
            self._state.expires_at = 0.0


class AsyncTokenCache:
    def __init__(
        self,
        *,
        fetch: Callable[[], Awaitable[dict[str, Any]]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._state = _TokenState()
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        async with self._lock:
            now = self._clock()
            if _needs_refresh(self._state, now):
                body = await self._fetch()
                _apply(self._state, body, self._clock())
            assert self._state.access_token is not None
            return self._state.access_token

    def invalidate(self) -> None:
        # Callers may invalidate from outside the lock. Assignment of two
        # simple attributes is atomic enough for our use — a concurrent
        # ``token()`` will still take the lock and re-check.
        self._state.access_token = None
        self._state.expires_at = 0.0
