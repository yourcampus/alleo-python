from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from alleo.client import AlleoClient
from alleo.errors import AuthenticationError, NetworkError, RateLimitError, ServerError
from tests.conftest import make_client

TOKEN_URL = "https://api.yourcampus.co/customer_api/v1/oauth/token"


def _token_response(body: dict | None = None) -> httpx.Response:
    body = body or {"access_token": "TOK", "token_type": "Bearer", "expires_in": 3600}
    return httpx.Response(200, json=body)


def test_env_fallback(monkeypatch):
    monkeypatch.setenv("ALLEO_ACCESS_KEY", "ak-env")
    monkeypatch.setenv("ALLEO_SECRET_KEY", "sk-env")
    monkeypatch.setenv("ALLEO_BASE_URL", "https://staging.example/customer_api/v1")

    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
        )
    )
    client = AlleoClient(http_client=httpx.Client(transport=transport))
    assert client._core.access_key == "ak-env"
    assert client._core.secret_key == "sk-env"
    assert client._core.base_url.endswith("/customer_api/v1")


def test_constructor_overrides_env(monkeypatch):
    monkeypatch.setenv("ALLEO_ACCESS_KEY", "ak-env")
    monkeypatch.setenv("ALLEO_SECRET_KEY", "sk-env")

    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    client = AlleoClient(
        access_key="ak-ctor",
        secret_key="sk-ctor",
        http_client=httpx.Client(transport=transport),
    )
    assert client._core.access_key == "ak-ctor"


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.delenv("ALLEO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("ALLEO_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="credentials"):
        AlleoClient()


def test_token_fetch_on_first_call():
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        assert req.headers.get("Authorization") == "Bearer TOK"
        return httpx.Response(200, json=[])

    client = make_client(handler)
    client._request("GET", "/companies")
    assert any(u.endswith("/oauth/token") for u in calls)


def test_401_triggers_refresh_and_retry_once():
    state = {"attempts": 0, "tokens_issued": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            state["tokens_issued"] += 1
            return _token_response(
                {
                    "access_token": f"T{state['tokens_issued']}",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
            )
        state["attempts"] += 1
        if state["attempts"] == 1:
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(200, json=[])

    client = make_client(handler)
    client._request("GET", "/companies")
    assert state["attempts"] == 2
    assert state["tokens_issued"] == 2  # initial + refresh


def test_401_twice_raises_authentication_error():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return httpx.Response(401, json={"detail": "nope"})

    client = make_client(handler)
    with pytest.raises(AuthenticationError):
        client._request("GET", "/companies")


def test_429_respects_retry_after_and_eventually_succeeds():
    attempts = {"n": 0}
    sleeps: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        attempts["n"] += 1
        if attempts["n"] <= 2:
            return httpx.Response(429, headers={"Retry-After": "3"}, json={"detail": "slow"})
        return httpx.Response(200, json=[])

    client = make_client(handler, sleep=sleeps.append)
    client._request("GET", "/companies")
    assert attempts["n"] == 3
    assert sleeps == [3.0, 3.0]


def test_429_exhausted_raises_rate_limit_error():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return httpx.Response(429, headers={"Retry-After": "1"}, json={"detail": "slow"})

    client = make_client(handler, max_retries=2, sleep=lambda _: None)
    with pytest.raises(RateLimitError) as exc_info:
        client._request("GET", "/companies")
    assert exc_info.value.retry_after == 1.0


def test_5xx_retries_exponentially_and_succeeds():
    attempts = {"n": 0}
    sleeps: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        attempts["n"] += 1
        if attempts["n"] <= 2:
            return httpx.Response(503, json={"detail": "down"})
        return httpx.Response(200, json=[])

    client = make_client(handler, sleep=sleeps.append)
    client._request("GET", "/companies")
    assert sleeps == [0.5, 1.0]


def test_5xx_exhausted_raises_server_error():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return httpx.Response(500, json={"detail": "boom"})

    client = make_client(handler, max_retries=2, sleep=lambda _: None)
    with pytest.raises(ServerError):
        client._request("GET", "/companies")


def test_network_error_retries_then_raises():
    tries = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        tries["n"] += 1
        raise httpx.ConnectError("dns go bye-bye")

    client = make_client(handler, max_retries=2, sleep=lambda _: None)
    with pytest.raises(NetworkError):
        client._request("GET", "/companies")
    assert tries["n"] == 3  # 1 initial + 2 retries


def test_last_rate_limit_populated():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "600",
                "X-RateLimit-Remaining": "42",
                "X-RateLimit-Reset": "60",
            },
            json=[],
        )

    client = make_client(handler)
    client._request("GET", "/companies")
    assert client.last_rate_limit is not None
    assert client.last_rate_limit.limit == 600
    assert client.last_rate_limit.remaining == 42


def test_context_manager_closes_owned_http():
    client = AlleoClient(access_key="ak", secret_key="sk")
    with client:
        pass
    assert client._http.is_closed


def test_context_manager_does_not_close_injected_http():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    http = httpx.Client(transport=transport)
    with AlleoClient(access_key="ak", secret_key="sk", http_client=http):
        pass
    assert not http.is_closed
    http.close()


def _auth_or(respond: Callable[[httpx.Request], httpx.Response]):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth/token"):
            return _token_response()
        return respond(req)

    return handler


def test_list_companies():
    def respond(req: httpx.Request) -> httpx.Response:
        assert req.method == "GET"
        assert req.url.path.endswith("/companies")
        return httpx.Response(200, json=[{"id": 1, "name": "Acme"}, {"id": 2, "name": None}])

    client = make_client(_auth_or(respond))
    companies = client.list_companies()
    assert len(companies) == 2
    assert companies[0].name == "Acme"
    assert companies[1].name is None


def test_list_employees_with_filters():
    captured = {}

    def respond(req: httpx.Request) -> httpx.Response:
        captured["url"] = req.url
        return httpx.Response(
            200,
            json={"data": [{"id": 1, "is_active": True}], "count": 1},
        )

    client = make_client(_auth_or(respond))
    resp = client.list_employees(
        42, skip=30, limit=30, is_active=True, company_group_id=1, search="jane"
    )
    assert resp.count == 1
    q = captured["url"].query.decode()
    assert "skip=30" in q
    assert "limit=30" in q
    assert "is_active=true" in q.lower()
    assert "company_group_id=1" in q
    assert "search=jane" in q


def test_list_employees_drops_none_filters():
    captured = {}

    def respond(req: httpx.Request) -> httpx.Response:
        captured["url"] = req.url
        return httpx.Response(200, json={"data": [], "count": 0})

    client = make_client(_auth_or(respond))
    client.list_employees(42)
    q = captured["url"].query.decode()
    assert "is_active" not in q
    assert "company_group_id" not in q
    assert "search" not in q


def test_get_employee():
    def respond(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/companies/42/employees/7")
        return httpx.Response(200, json={"id": 7, "is_active": True})

    client = make_client(_auth_or(respond))
    emp = client.get_employee(42, 7)
    assert emp.id == 7


def test_create_employee_accepts_dict():
    import json as jsonlib

    captured = {}

    def respond(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content
        return httpx.Response(201, json={"id": 7, "is_active": True})

    client = make_client(_auth_or(respond))
    emp = client.create_employee(
        42, {"email": "jane@acme.com", "first_name": "Jane", "last_name": "Doe"}
    )
    assert emp.id == 7
    sent = jsonlib.loads(captured["body"])
    assert sent["email"] == "jane@acme.com"


def test_create_employee_accepts_model():
    from alleo import EmployeeCreate

    def respond(req: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": 7, "is_active": True})

    client = make_client(_auth_or(respond))
    emp = client.create_employee(
        42, EmployeeCreate(email="jane@acme.com", first_name="Jane", last_name="Doe")
    )
    assert emp.id == 7


def test_update_employee_patch_excludes_unset():
    import json as jsonlib

    from alleo import EmployeeEdit

    captured = {}

    def respond(req: httpx.Request) -> httpx.Response:
        assert req.method == "PATCH"
        captured["body"] = req.content
        return httpx.Response(200, json={"id": 7, "is_active": True})

    client = make_client(_auth_or(respond))
    client.update_employee(42, 7, EmployeeEdit(last_name="Doe-Smith"))
    sent = jsonlib.loads(captured["body"])
    assert sent == {"last_name": "Doe-Smith"}  # no other keys


def test_update_employee_explicit_null_kept():
    import json as jsonlib

    from alleo import EmployeeEdit

    captured = {}

    def respond(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content
        return httpx.Response(200, json={"id": 7, "is_active": True})

    client = make_client(_auth_or(respond))
    client.update_employee(42, 7, EmployeeEdit(external_id=None))
    sent = jsonlib.loads(captured["body"])
    assert sent == {"external_id": None}


def test_deactivate_employee():
    def respond(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert req.url.path.endswith("/companies/42/employees/7/deactivate")
        return httpx.Response(200, json={"id": 7, "is_active": False})

    client = make_client(_auth_or(respond))
    emp = client.deactivate_employee(42, 7)
    assert emp.is_active is False


def test_activate_employee():
    def respond(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert req.url.path.endswith("/companies/42/employees/7/activate")
        return httpx.Response(200, json={"id": 7, "is_active": True})

    client = make_client(_auth_or(respond))
    emp = client.activate_employee(42, 7)
    assert emp.is_active is True


def test_list_company_groups():
    def respond(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/companies/42/groups")
        return httpx.Response(200, json=[{"id": 1, "name": "Eng"}])

    client = make_client(_auth_or(respond))
    groups = client.list_company_groups(42)
    assert groups[0].name == "Eng"


def test_conflict_error_on_duplicate_email():
    from alleo.errors import ConflictError

    def respond(req: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Email address already exists"})

    client = make_client(_auth_or(respond))
    with pytest.raises(ConflictError):
        client.create_employee(42, {"email": "x@y.z", "first_name": "X", "last_name": "Y"})
