import asyncio

import pytest

from alleo._auth import AsyncTokenCache, SyncTokenCache


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------- Sync ----------


def test_sync_token_rejects_missing_expires_in():
    def fetcher():
        return {"access_token": "t", "token_type": "Bearer"}

    cache = SyncTokenCache(fetch=fetcher, clock=FakeClock())
    with pytest.raises(ValueError, match="expires_in"):
        cache.token()


def test_sync_token_rejects_missing_access_token():
    def fetcher():
        return {"expires_in": 3600}

    cache = SyncTokenCache(fetch=fetcher, clock=FakeClock())
    with pytest.raises(ValueError, match="access_token"):
        cache.token()


def test_sync_token_first_call_fetches():
    clock = FakeClock()
    calls = []

    def fetcher():
        calls.append(True)
        return {"access_token": "t1", "token_type": "Bearer", "expires_in": 3600}

    cache = SyncTokenCache(fetch=fetcher, clock=clock)
    assert cache.token() == "t1"
    assert len(calls) == 1


def test_sync_token_reused_until_near_expiry():
    clock = FakeClock()
    n = iter(range(100))

    def fetcher():
        i = next(n)
        return {"access_token": f"t{i}", "token_type": "Bearer", "expires_in": 3600}

    cache = SyncTokenCache(fetch=fetcher, clock=clock)
    assert cache.token() == "t0"
    clock.advance(3000)  # still fresh
    assert cache.token() == "t0"


def test_sync_token_refreshed_within_60s_of_expiry():
    clock = FakeClock()
    n = iter(range(100))

    def fetcher():
        i = next(n)
        return {"access_token": f"t{i}", "token_type": "Bearer", "expires_in": 3600}

    cache = SyncTokenCache(fetch=fetcher, clock=clock)
    assert cache.token() == "t0"
    # 3600 - 59 seconds in: within the 60s refresh margin
    clock.advance(3541)
    assert cache.token() == "t1"


def test_sync_token_invalidate_forces_refetch():
    clock = FakeClock()
    n = iter(range(100))

    def fetcher():
        i = next(n)
        return {"access_token": f"t{i}", "token_type": "Bearer", "expires_in": 3600}

    cache = SyncTokenCache(fetch=fetcher, clock=clock)
    assert cache.token() == "t0"
    cache.invalidate()
    assert cache.token() == "t1"


# ---------- Async ----------


@pytest.mark.asyncio
async def test_async_token_first_call_fetches():
    clock = FakeClock()
    calls = []

    async def fetcher():
        calls.append(True)
        return {"access_token": "t1", "token_type": "Bearer", "expires_in": 3600}

    cache = AsyncTokenCache(fetch=fetcher, clock=clock)
    assert await cache.token() == "t1"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_async_token_reused_until_near_expiry():
    clock = FakeClock()
    n = iter(range(100))

    async def fetcher():
        i = next(n)
        return {"access_token": f"t{i}", "token_type": "Bearer", "expires_in": 3600}

    cache = AsyncTokenCache(fetch=fetcher, clock=clock)
    assert await cache.token() == "t0"
    clock.advance(3000)
    assert await cache.token() == "t0"


@pytest.mark.asyncio
async def test_async_token_refreshed_within_60s_of_expiry():
    clock = FakeClock()
    n = iter(range(100))

    async def fetcher():
        i = next(n)
        return {"access_token": f"t{i}", "token_type": "Bearer", "expires_in": 3600}

    cache = AsyncTokenCache(fetch=fetcher, clock=clock)
    assert await cache.token() == "t0"
    clock.advance(3541)
    assert await cache.token() == "t1"


@pytest.mark.asyncio
async def test_async_token_invalidate_forces_refetch():
    clock = FakeClock()
    n = iter(range(100))

    async def fetcher():
        i = next(n)
        return {"access_token": f"t{i}", "token_type": "Bearer", "expires_in": 3600}

    cache = AsyncTokenCache(fetch=fetcher, clock=clock)
    assert await cache.token() == "t0"
    cache.invalidate()
    assert await cache.token() == "t1"


@pytest.mark.asyncio
async def test_async_concurrent_callers_share_one_fetch():
    clock = FakeClock()
    calls = 0

    async def fetcher():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)  # give other callers a chance to stack up
        return {"access_token": "t", "token_type": "Bearer", "expires_in": 3600}

    cache = AsyncTokenCache(fetch=fetcher, clock=clock)
    await asyncio.gather(*(cache.token() for _ in range(10)))
    assert calls == 1
