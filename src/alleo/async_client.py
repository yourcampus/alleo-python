"""Asynchronous Alleo client. Mirrors AlleoClient with awaits."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from types import TracebackType
from typing import Any

import httpx
from typing_extensions import Self

from alleo._auth import AsyncTokenCache
from alleo._core import DEFAULT_BASE_URL, _Core
from alleo._pagination import paginate_employees_async
from alleo._version import __version__
from alleo.errors import AuthenticationError, NetworkError
from alleo.models import (
    CompanyGroupOut,
    CompanyOut,
    EmployeeCreate,
    EmployeeEdit,
    EmployeeListResponse,
    EmployeeOut,
    RateLimit,
)


class AsyncAlleoClient:
    """Asynchronous client for the Alleo Customer API."""

    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        http_client: httpx.AsyncClient | None = None,
        logger: Callable[[str], None] | None = None,
        _clock: Callable[[], float] | None = None,
        _sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        ak = access_key or os.environ.get("ALLEO_ACCESS_KEY")
        sk = secret_key or os.environ.get("ALLEO_SECRET_KEY")
        bu = base_url or os.environ.get("ALLEO_BASE_URL") or DEFAULT_BASE_URL
        if not ak or not sk:
            raise ValueError(
                "Alleo SDK: missing credentials. Pass access_key / secret_key "
                "or set ALLEO_ACCESS_KEY / ALLEO_SECRET_KEY."
            )
        self._core = _Core(
            base_url=bu,
            access_key=ak,
            secret_key=sk,
            timeout=timeout_seconds,
            max_retries=max_retries,
            user_agent=f"alleo-sdk-python/{__version__}",
            logger=logger,
            clock=_clock or time.monotonic,
        )
        self._http = (
            http_client if http_client is not None else httpx.AsyncClient(timeout=timeout_seconds)
        )
        self._owns_http = http_client is None
        self._sleep: Callable[[float], Awaitable[None]] = _sleep or asyncio.sleep
        self._auth = AsyncTokenCache(
            fetch=self._fetch_token,
            clock=self._core.clock,
        )
        self.last_rate_limit: RateLimit | None = None

    # ---------- lifecycle ----------

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ---------- token endpoint ----------

    async def _fetch_token(self) -> dict[str, Any]:
        req = self._core.build_request(
            "POST",
            "/oauth/token",
            form={
                "grant_type": "client_credentials",
                "client_id": self._core.access_key,
                "client_secret": self._core.secret_key,
            },
        )
        try:
            resp = await self._http.send(req)
        except httpx.TransportError as e:
            raise NetworkError(f"token fetch failed: {e.__class__.__name__}") from e
        if resp.status_code != 200:
            raise self._core.map_error(resp)
        result: dict[str, Any] = resp.json()
        return result

    # ---------- request loop ----------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        auth_required: bool = True,
    ) -> httpx.Response:
        # 401 refresh-retry (blueprint §2.3) does NOT consume `attempt`, so an
        # expired-token recovery is independent of the 3-retry budget for
        # transient failures (blueprint §4.3).
        refreshed_after_401 = False
        attempt = 0
        while True:
            req = self._core.build_request(method, path, params=params, json=json)
            if auth_required:
                req.headers["Authorization"] = f"Bearer {await self._auth.token()}"

            try:
                resp = await self._http.send(req)
            except httpx.TransportError as e:
                delay = self._core.should_retry(attempt, None, network_error=True)
                if delay is None:
                    raise NetworkError(f"network error: {e.__class__.__name__}") from e
                await self._sleep(delay)
                attempt += 1
                continue

            self.last_rate_limit = self._core.parse_rate_limit(resp)

            if resp.status_code == 401 and auth_required and not refreshed_after_401:
                refreshed_after_401 = True
                self._auth.invalidate()
                continue
            if resp.status_code == 401:
                raise AuthenticationError(
                    self._core.map_error(resp).message,
                    status_code=401,
                    response_body=_safe_json(resp),
                )

            delay = self._core.should_retry(attempt, resp)
            if delay is None:
                if resp.is_success:
                    return resp
                raise self._core.map_error(resp)
            await self._sleep(delay)
            attempt += 1

    # ---------- endpoint methods ----------

    async def list_companies(self) -> list[CompanyOut]:
        resp = await self._request("GET", "/companies")
        return [CompanyOut.model_validate(row) for row in resp.json()]

    async def list_employees(
        self,
        company_id: int,
        *,
        skip: int = 0,
        limit: int = 30,
        is_active: bool | None = None,
        company_group_id: int | None = None,
        search: str | None = None,
    ) -> EmployeeListResponse:
        resp = await self._request(
            "GET",
            f"/companies/{company_id}/employees",
            params={
                "skip": skip,
                "limit": limit,
                "is_active": _bool_or_none(is_active),
                "company_group_id": company_group_id,
                "search": search,
            },
        )
        return EmployeeListResponse.model_validate(resp.json())

    async def get_employee(self, company_id: int, employee_id: int) -> EmployeeOut:
        resp = await self._request("GET", f"/companies/{company_id}/employees/{employee_id}")
        return EmployeeOut.model_validate(resp.json())

    async def create_employee(
        self, company_id: int, body: EmployeeCreate | Mapping[str, Any]
    ) -> EmployeeOut:
        payload = _dump_create(body)
        resp = await self._request("POST", f"/companies/{company_id}/employees", json=payload)
        return EmployeeOut.model_validate(resp.json())

    async def update_employee(
        self,
        company_id: int,
        employee_id: int,
        body: EmployeeEdit | Mapping[str, Any],
    ) -> EmployeeOut:
        payload = _dump_edit(body)
        resp = await self._request(
            "PATCH",
            f"/companies/{company_id}/employees/{employee_id}",
            json=payload,
        )
        return EmployeeOut.model_validate(resp.json())

    async def deactivate_employee(self, company_id: int, employee_id: int) -> EmployeeOut:
        resp = await self._request(
            "POST", f"/companies/{company_id}/employees/{employee_id}/deactivate"
        )
        return EmployeeOut.model_validate(resp.json())

    async def activate_employee(self, company_id: int, employee_id: int) -> EmployeeOut:
        resp = await self._request(
            "POST", f"/companies/{company_id}/employees/{employee_id}/activate"
        )
        return EmployeeOut.model_validate(resp.json())

    async def list_company_groups(self, company_id: int) -> list[CompanyGroupOut]:
        resp = await self._request("GET", f"/companies/{company_id}/groups")
        return [CompanyGroupOut.model_validate(row) for row in resp.json()]

    def list_employees_iter(
        self,
        company_id: int,
        *,
        is_active: bool | None = None,
        company_group_id: int | None = None,
        search: str | None = None,
    ) -> AsyncIterator[EmployeeOut]:
        async def fetch_page(skip: int, limit: int) -> EmployeeListResponse:
            return await self.list_employees(
                company_id,
                skip=skip,
                limit=limit,
                is_active=is_active,
                company_group_id=company_group_id,
                search=search,
            )

        return paginate_employees_async(fetch_page)


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def _bool_or_none(value: bool | None) -> str | None:
    if value is None:
        return None
    return "true" if value else "false"


def _dump_create(body: EmployeeCreate | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(body, EmployeeCreate):
        return body.model_dump(mode="json")
    return EmployeeCreate.model_validate(body).model_dump(mode="json")


def _dump_edit(body: EmployeeEdit | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(body, EmployeeEdit):
        return body.model_dump(mode="json", exclude_unset=True)
    return EmployeeEdit.model_validate(body).model_dump(mode="json", exclude_unset=True)
