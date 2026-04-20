"""Lazy paginators for list endpoints (blueprint §5)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

from alleo.models import EmployeeListResponse, EmployeeOut

PAGE_SIZE = 100


def paginate_employees_sync(
    fetch_page: Callable[[int, int], EmployeeListResponse],
) -> Iterator[EmployeeOut]:
    skip = 0
    while True:
        page = fetch_page(skip, PAGE_SIZE)
        if not page.data:
            return
        yield from page.data
        skip += len(page.data)
        if skip >= page.count:
            return


async def paginate_employees_async(
    fetch_page: Callable[[int, int], Awaitable[EmployeeListResponse]],
) -> AsyncIterator[EmployeeOut]:
    skip = 0
    while True:
        page = await fetch_page(skip, PAGE_SIZE)
        if not page.data:
            return
        for row in page.data:
            yield row
        skip += len(page.data)
        if skip >= page.count:
            return
