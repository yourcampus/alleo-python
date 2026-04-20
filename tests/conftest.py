"""Shared test helpers: MockTransport-backed clients and a fake clock."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx

from alleo.async_client import AsyncAlleoClient  # forward-looking import
from alleo.client import AlleoClient


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler,
    *,
    access_key: str = "ak",
    secret_key: str = "sk",
    base_url: str = "https://api.yourcampus.co/customer_api/v1",
    max_retries: int = 3,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> AlleoClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return AlleoClient(
        access_key=access_key,
        secret_key=secret_key,
        base_url=base_url,
        max_retries=max_retries,
        http_client=http,
        _clock=clock,
        _sleep=sleep,
    )


def make_async_client(
    handler: Handler,
    *,
    access_key: str = "ak",
    secret_key: str = "sk",
    base_url: str = "https://api.yourcampus.co/customer_api/v1",
    max_retries: int = 3,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> AsyncAlleoClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return AsyncAlleoClient(
        access_key=access_key,
        secret_key=secret_key,
        base_url=base_url,
        max_retries=max_retries,
        http_client=http,
        _clock=clock,
        _sleep=sleep,
    )
