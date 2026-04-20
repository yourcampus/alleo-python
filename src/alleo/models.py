"""Pydantic v2 models for the Alleo SDK (blueprint §8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CompanyOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str | None = None


class CompanyGroupOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str | None = None


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=100)
    first_name: str = Field(max_length=1000)
    last_name: str = Field(max_length=1000)
    prefix: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default="en", max_length=1000)
    company_group_id: int | None = None
    birthday: date | None = None
    work_anniversary: date | None = None
    private_email: EmailStr | None = Field(default=None, max_length=100)
    external_id: str | None = Field(default=None, max_length=1000)


class EmployeeEdit(BaseModel):
    """All optional. Use ``model_dump(exclude_unset=True)`` for PATCH bodies.

    Setting a field to ``None`` explicitly (e.g. ``external_id=None``) is
    distinct from not setting it at all — explicit-null is included in the
    dump, unset is not.
    """

    model_config = ConfigDict(extra="forbid")
    email: EmailStr | None = Field(default=None, max_length=100)
    first_name: str | None = Field(default=None, max_length=1000)
    last_name: str | None = Field(default=None, max_length=1000)
    prefix: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, max_length=1000)
    company_group_id: int | None = None
    birthday: date | None = None
    work_anniversary: date | None = None
    private_email: EmailStr | None = Field(default=None, max_length=100)
    external_id: str | None = Field(default=None, max_length=1000)


class EmployeeOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    prefix: str | None = None
    language: str | None = None
    private_email: str | None = None
    is_active: bool
    company_group_id: int | None = None
    group_name: str | None = None
    external_id: str | None = None
    registration_date: datetime | None = None
    offboarding_date: datetime | None = None
    birthday: date | None = None
    work_anniversary: date | None = None
    last_active_date: datetime | None = None


class EmployeeListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: list[EmployeeOut]
    count: int


@dataclass(frozen=True)
class RateLimit:
    """Parsed from X-RateLimit-* response headers."""

    limit: int | None
    remaining: int | None
    reset_seconds: int | None
