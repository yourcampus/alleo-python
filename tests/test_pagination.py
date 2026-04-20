from __future__ import annotations

import httpx
import pytest

from tests.conftest import make_async_client, make_client


def _token_response() -> httpx.Response:
    return httpx.Response(
        200, json={"access_token": "TOK", "token_type": "Bearer", "expires_in": 3600}
    )


def _paged_handler(total: int):
    """Handler that serves ``total`` employees across pages of limit=100."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        skip = int(req.url.params.get("skip", 0))
        limit = int(req.url.params.get("limit", 30))
        page = [{"id": i, "is_active": True} for i in range(skip, min(skip + limit, total))]
        return httpx.Response(200, json={"data": page, "count": total})

    return handler


def test_iter_yields_every_row_multipage():
    client = make_client(_paged_handler(250))
    ids = [emp.id for emp in client.list_employees_iter(42)]
    assert ids == list(range(250))


def test_iter_single_page():
    client = make_client(_paged_handler(7))
    assert [e.id for e in client.list_employees_iter(42)] == list(range(7))


def test_iter_empty():
    client = make_client(_paged_handler(0))
    assert list(client.list_employees_iter(42)) == []


def test_iter_passes_filters():
    captured: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        captured.append(req.url.query.decode())
        return httpx.Response(200, json={"data": [], "count": 0})

    client = make_client(handler)
    list(client.list_employees_iter(42, is_active=True, search="jane"))
    # Exactly one page requested (count=0 stops after first).
    assert len(captured) == 1
    assert "is_active=true" in captured[0].lower()
    assert "search=jane" in captured[0]
    assert "limit=100" in captured[0]


def test_iter_is_lazy():
    """Iterator does not eagerly fetch all pages."""
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        calls["n"] += 1
        skip = int(req.url.params.get("skip", 0))
        page = [{"id": skip, "is_active": True}]
        return httpx.Response(200, json={"data": page, "count": 1000})

    client = make_client(handler)
    it = client.list_employees_iter(42)
    next(it)
    assert calls["n"] == 1  # only the first page has been fetched


@pytest.mark.asyncio
async def test_async_iter_multipage():
    client = make_async_client(_paged_handler(250))
    ids = [emp.id async for emp in client.list_employees_iter(42)]
    assert ids == list(range(250))
    await client.aclose()


@pytest.mark.asyncio
async def test_async_iter_empty():
    client = make_async_client(_paged_handler(0))
    out = [e async for e in client.list_employees_iter(42)]
    assert out == []
    await client.aclose()
