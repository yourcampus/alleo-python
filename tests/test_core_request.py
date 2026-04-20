import httpx

from alleo._core import _Core
from alleo.models import RateLimit


def make_core(**overrides):
    defaults = dict(
        base_url="https://api.yourcampus.co/customer_api/v1",
        access_key="ak",
        secret_key="sk",
        timeout=30.0,
        max_retries=3,
        user_agent="alleo-sdk-python/0.1.1",
        logger=None,
    )
    defaults.update(overrides)
    return _Core(**defaults)


def test_build_request_get_no_params():
    core = make_core()
    req = core.build_request("GET", "/companies")
    assert req.method == "GET"
    assert str(req.url) == "https://api.yourcampus.co/customer_api/v1/companies"
    assert req.headers["User-Agent"] == "alleo-sdk-python/0.1.1"
    assert req.headers["Accept"] == "application/json"


def test_build_request_with_params_drops_none():
    core = make_core()
    req = core.build_request(
        "GET",
        "/companies/1/employees",
        params={"skip": 0, "limit": 30, "is_active": None, "search": "ja"},
    )
    assert "is_active" not in req.url.query.decode()
    assert "skip=0" in req.url.query.decode()
    assert "limit=30" in req.url.query.decode()
    assert "search=ja" in req.url.query.decode()


def test_build_request_json_body():
    core = make_core()
    req = core.build_request("POST", "/x", json={"a": 1})
    assert req.headers["Content-Type"] == "application/json"
    assert req.content == b'{"a": 1}'


def test_build_request_form_body_for_token():
    core = make_core()
    req = core.build_request("POST", "/oauth/token", form={"grant_type": "client_credentials"})
    assert req.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert b"grant_type=client_credentials" in req.content


def test_build_request_strips_leading_slash():
    core = make_core()
    req = core.build_request("GET", "companies")  # no leading slash
    assert str(req.url) == "https://api.yourcampus.co/customer_api/v1/companies"


def test_build_request_base_url_without_trailing_slash_ok():
    core = make_core(base_url="https://staging.example.com/customer_api/v1")
    req = core.build_request("GET", "/companies")
    assert str(req.url) == "https://staging.example.com/customer_api/v1/companies"


def test_parse_rate_limit_populates_when_headers_present():
    core = make_core()
    resp = httpx.Response(
        200,
        headers={
            "X-RateLimit-Limit": "600",
            "X-RateLimit-Remaining": "599",
            "X-RateLimit-Reset": "60",
        },
    )
    rl = core.parse_rate_limit(resp)
    assert rl == RateLimit(limit=600, remaining=599, reset_seconds=60)


def test_parse_rate_limit_none_when_missing():
    core = make_core()
    resp = httpx.Response(200)
    rl = core.parse_rate_limit(resp)
    assert rl == RateLimit(limit=None, remaining=None, reset_seconds=None)


def test_parse_rate_limit_ignores_malformed():
    core = make_core()
    resp = httpx.Response(200, headers={"X-RateLimit-Limit": "not-a-number"})
    rl = core.parse_rate_limit(resp)
    assert rl.limit is None
