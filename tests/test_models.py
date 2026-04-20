from datetime import date, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from alleo.models import (
    CompanyGroupOut,
    CompanyOut,
    EmployeeCreate,
    EmployeeEdit,
    EmployeeListResponse,
    EmployeeOut,
    RateLimit,
)


def test_company_out_parses():
    c = CompanyOut.model_validate({"id": 1, "name": "Acme"})
    assert c.id == 1
    assert c.name == "Acme"


def test_company_out_allows_null_name():
    c = CompanyOut.model_validate({"id": 1, "name": None})
    assert c.name is None


def test_company_group_out_parses():
    g = CompanyGroupOut.model_validate({"id": 2, "name": "Engineering"})
    assert g.id == 2
    assert g.name == "Engineering"


def test_employee_create_minimal():
    body = EmployeeCreate(email="jane@acme.com", first_name="Jane", last_name="Doe")
    assert body.email == "jane@acme.com"
    assert body.language == "en"  # default


def test_employee_create_rejects_bad_email():
    with pytest.raises(PydanticValidationError):
        EmployeeCreate(email="not-an-email", first_name="J", last_name="D")


def test_employee_create_rejects_extra_fields():
    with pytest.raises(PydanticValidationError):
        EmployeeCreate(
            email="jane@acme.com",
            first_name="Jane",
            last_name="Doe",
            unknown_field="oops",
        )


def test_employee_create_full():
    body = EmployeeCreate(
        email="jane@acme.com",
        first_name="Jane",
        last_name="Doe",
        prefix="Ms.",
        language="nl",
        company_group_id=1,
        birthday=date(1990, 5, 15),
        work_anniversary=date(2020, 1, 1),
        private_email="jane@home.com",
        external_id="HRIS-12345",
    )
    assert body.birthday == date(1990, 5, 15)
    assert body.external_id == "HRIS-12345"


def test_employee_edit_all_optional():
    body = EmployeeEdit()
    assert body.model_dump(exclude_unset=True) == {}


def test_employee_edit_partial_dump_excludes_unset():
    body = EmployeeEdit(last_name="Doe-Smith")
    assert body.model_dump(exclude_unset=True) == {"last_name": "Doe-Smith"}


def test_employee_edit_explicit_null_is_kept():
    body = EmployeeEdit(external_id=None)
    dumped = body.model_dump(exclude_unset=True)
    assert dumped == {"external_id": None}


def test_employee_out_parses_full():
    data = {
        "id": 42,
        "email": "jane@acme.com",
        "first_name": "Jane",
        "last_name": "Doe",
        "prefix": None,
        "language": "en",
        "private_email": None,
        "is_active": True,
        "company_group_id": 1,
        "group_name": "Engineering",
        "external_id": "HRIS-12345",
        "registration_date": "2024-01-01T09:00:00",
        "offboarding_date": None,
        "birthday": "1990-05-15",
        "work_anniversary": None,
        "last_active_date": "2026-04-18T12:34:56",
    }
    emp = EmployeeOut.model_validate(data)
    assert emp.id == 42
    assert emp.is_active is True
    assert emp.registration_date == datetime(2024, 1, 1, 9, 0, 0)
    assert emp.birthday == date(1990, 5, 15)


def test_employee_out_ignores_unknown_server_fields():
    data = {
        "id": 1,
        "is_active": True,
        "brand_new_server_field": "tomorrow",
    }
    emp = EmployeeOut.model_validate(data)
    assert emp.id == 1
    assert not hasattr(emp, "brand_new_server_field")


def test_employee_list_response():
    resp = EmployeeListResponse.model_validate(
        {"data": [{"id": 1, "is_active": True}], "count": 17}
    )
    assert resp.count == 17
    assert len(resp.data) == 1


def test_rate_limit_dataclass():
    rl = RateLimit(limit=600, remaining=599, reset_seconds=60)
    assert rl.limit == 600
    assert rl.remaining == 599
    assert rl.reset_seconds == 60


def test_rate_limit_all_none():
    rl = RateLimit(limit=None, remaining=None, reset_seconds=None)
    assert rl.limit is None
