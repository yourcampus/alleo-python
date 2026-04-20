from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from alleo.async_client import AsyncAlleoClient
from alleo.errors import AuthenticationError, NetworkError, ServerError
from tests.conftest import make_async_client


def _token_response(body: dict | None = None) -> httpx.Response:
    body = body or {"access_token": "TOK", "token_type": "Bearer", "expires_in": 3600}
    return httpx.Response(200, json=body)


@pytest.mark.asyncio
async def test_env_fallback(monkeypatch):
    monkeypatch.setenv("ALLEO_ACCESS_KEY", "ak-env")
    monkeypatch.setenv("ALLEO_SECRET_KEY", "sk-env")
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
        )
    )
    client = AsyncAlleoClient(http_client=httpx.AsyncClient(transport=transport))
    assert client._core.access_key == "ak-env"
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_credentials_raises(monkeypatch):
    monkeypatch.delenv("ALLEO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("ALLEO_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="credentials"):
        AsyncAlleoClient()


@pytest.mark.asyncio
async def test_token_fetch_then_call():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        assert req.headers.get("Authorization") == "Bearer TOK"
        return httpx.Response(200, json=[])

    client = make_async_client(handler)
    resp = await client._request("GET", "/companies")
    assert resp.status_code == 200
    await client.aclose()


@pytest.mark.asyncio
async def test_401_retry_once_then_auth_error():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return httpx.Response(401, json={"detail": "nope"})

    client = make_async_client(handler)
    with pytest.raises(AuthenticationError):
        await client._request("GET", "/companies")
    await client.aclose()


@pytest.mark.asyncio
async def test_429_retry_with_retry_after():
    attempts = {"n": 0}
    sleeps: list[float] = []

    async def asleep(s: float) -> None:
        sleeps.append(s)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        attempts["n"] += 1
        if attempts["n"] <= 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"detail": "slow"})
        return httpx.Response(200, json=[])

    client = make_async_client(handler, sleep=asleep)
    await client._request("GET", "/companies")
    assert sleeps == [2.0]
    await client.aclose()


@pytest.mark.asyncio
async def test_5xx_exhausted_raises_server_error():
    async def noop_sleep(_: float) -> None:
        return None

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return httpx.Response(500, json={"detail": "boom"})

    client = make_async_client(handler, max_retries=1, sleep=noop_sleep)
    with pytest.raises(ServerError):
        await client._request("GET", "/companies")
    await client.aclose()


@pytest.mark.asyncio
async def test_network_error_retries_then_raises():
    tries = {"n": 0}

    async def noop_sleep(_: float) -> None:
        return None

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        tries["n"] += 1
        raise httpx.ConnectError("dns")

    client = make_async_client(handler, max_retries=2, sleep=noop_sleep)
    with pytest.raises(NetworkError):
        await client._request("GET", "/companies")
    assert tries["n"] == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_last_rate_limit_populated():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "600",
                "X-RateLimit-Remaining": "5",
                "X-RateLimit-Reset": "60",
            },
            json=[],
        )

    client = make_async_client(handler)
    await client._request("GET", "/companies")
    assert client.last_rate_limit is not None
    assert client.last_rate_limit.remaining == 5
    await client.aclose()


@pytest.mark.asyncio
async def test_async_context_manager_closes_owned():
    client = AsyncAlleoClient(access_key="ak", secret_key="sk")
    async with client:
        pass
    assert client._http.is_closed


@pytest.mark.asyncio
async def test_async_context_manager_does_not_close_injected():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    http = httpx.AsyncClient(transport=transport)
    async with AsyncAlleoClient(access_key="ak", secret_key="sk", http_client=http):
        pass
    assert not http.is_closed
    await http.aclose()


def _auth_or(respond: Callable[[httpx.Request], httpx.Response]):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return respond(req)

    return handler


@pytest.mark.asyncio
async def test_list_companies_async():
    def respond(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1, "name": "Acme"}])

    client = make_async_client(_auth_or(respond))
    companies = await client.list_companies()
    assert companies[0].name == "Acme"
    await client.aclose()


@pytest.mark.asyncio
async def test_list_employees_async():
    def respond(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": 1, "is_active": True}], "count": 1})

    client = make_async_client(_auth_or(respond))
    resp = await client.list_employees(42, is_active=True)
    assert resp.count == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_get_employee_async():
    def respond(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/companies/42/employees/7")
        return httpx.Response(200, json={"id": 7, "is_active": True})

    client = make_async_client(_auth_or(respond))
    emp = await client.get_employee(42, 7)
    assert emp.id == 7
    await client.aclose()


@pytest.mark.asyncio
async def test_create_employee_async_dict():
    def respond(req: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": 7, "is_active": True})

    client = make_async_client(_auth_or(respond))
    emp = await client.create_employee(
        42, {"email": "jane@acme.com", "first_name": "J", "last_name": "D"}
    )
    assert emp.id == 7
    await client.aclose()


@pytest.mark.asyncio
async def test_update_employee_async_excludes_unset():
    import json as jsonlib

    from alleo import EmployeeEdit

    captured = {}

    def respond(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content
        return httpx.Response(200, json={"id": 7, "is_active": True})

    client = make_async_client(_auth_or(respond))
    await client.update_employee(42, 7, EmployeeEdit(last_name="Doe-Smith"))
    assert jsonlib.loads(captured["body"]) == {"last_name": "Doe-Smith"}
    await client.aclose()


@pytest.mark.asyncio
async def test_deactivate_and_activate_async():
    def respond(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        active = req.url.path.endswith("/activate")
        return httpx.Response(200, json={"id": 7, "is_active": active})

    client = make_async_client(_auth_or(respond))
    emp = await client.deactivate_employee(42, 7)
    assert emp.is_active is False
    emp = await client.activate_employee(42, 7)
    assert emp.is_active is True
    await client.aclose()


@pytest.mark.asyncio
async def test_list_company_groups_async():
    def respond(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1, "name": "Eng"}])

    client = make_async_client(_auth_or(respond))
    groups = await client.list_company_groups(42)
    assert groups[0].id == 1
    await client.aclose()
