# Alleo Python SDK

Official Python SDK for the [Alleo Customer API](https://api.yourcampus.co/customer_api/docs).


## Install

```bash
pip install alleo
# or
uv add alleo
```

Requires Python 3.10+.

## Quickstart — sync

```python
from alleo import AlleoClient

with AlleoClient(access_key="...", secret_key="...") as client:
    companies = client.list_companies()
    for company in companies:
        print(company.id, company.name)

    # Iterate every employee across all pages lazily.
    for employee in client.list_employees_iter(company_id=companies[0].id, is_active=True):
        print(employee.id, employee.email)
```

Credentials can also come from the environment:

```bash
export ALLEO_ACCESS_KEY=...
export ALLEO_SECRET_KEY=...
# optional
```

Then:

```python
with AlleoClient() as client:
    ...
```

## Quickstart — async

```python
import asyncio
from alleo import AsyncAlleoClient

async def main():
    async with AsyncAlleoClient() as client:
        companies = await client.list_companies()
        async for emp in client.list_employees_iter(companies[0].id):
            print(emp.id, emp.email)

asyncio.run(main())
```

## Creating and updating employees

```python
from alleo import AlleoClient, EmployeeCreate, EmployeeEdit

with AlleoClient() as client:
    new_emp = client.create_employee(
        company_id=42,
        body=EmployeeCreate(
            email="jane.doe@acme.com",
            first_name="Jane",
            last_name="Doe",
            language="en",
            company_group_id=1,
        ),
    )

    # PATCH — only the set fields are sent.
    client.update_employee(42, new_emp.id, EmployeeEdit(last_name="Doe-Smith"))

    client.deactivate_employee(42, new_emp.id)
```

Bodies also accept plain dicts.

## Error handling

```python
from alleo import AlleoClient, ConflictError, RateLimitError, ValidationError

with AlleoClient() as client:
    try:
        client.create_employee(42, {"email": "dup@acme.com", "first_name": "D", "last_name": "U"})
    except ConflictError as e:
        # 409 — duplicate email. e.message = server's "detail", e.response_body has the full body.
        ...
    except ValidationError as e:
        # 400 or 422. For 422 the message is a flattened "loc: msg" line per field.
        ...
    except RateLimitError as e:
        # Raised only after the SDK has exhausted its automatic retries.
        # e.retry_after has the server's last Retry-After in seconds.
        ...
```

All errors derive from `AlleoError`. See [`src/alleo/errors.py`](src/alleo/errors.py) for the full taxonomy.

## Rate limits

After every call, the last observed rate-limit headers are available on the client:

```python
print(client.last_rate_limit)  # RateLimit(limit=600, remaining=599, reset_seconds=60)
```

The SDK retries `429` automatically (respecting `Retry-After`) up to `max_retries=3` before raising `RateLimitError`.

## Blueprint version

This SDK targets `blueprint_version = "1"`. If the server publishes a v2 blueprint, upgrade to a matching SDK major version.

## License

MIT — see [`LICENSE`](LICENSE).
