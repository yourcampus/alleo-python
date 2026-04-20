from alleo._version import __version__
from alleo.async_client import AsyncAlleoClient
from alleo.client import AlleoClient
from alleo.errors import (
    AlleoError,
    AlleoPermissionError,
    AuthenticationError,
    ConflictError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from alleo.models import (
    CompanyGroupOut,
    CompanyOut,
    EmployeeCreate,
    EmployeeEdit,
    EmployeeListResponse,
    EmployeeOut,
    RateLimit,
)

PermissionError = AlleoPermissionError  # noqa: A001

__all__ = [
    "__version__",
    "AlleoClient",
    "AlleoError",
    "AlleoPermissionError",
    "AsyncAlleoClient",
    "AuthenticationError",
    "CompanyGroupOut",
    "CompanyOut",
    "ConflictError",
    "EmployeeCreate",
    "EmployeeEdit",
    "EmployeeListResponse",
    "EmployeeOut",
    "NetworkError",
    "NotFoundError",
    "PermissionError",
    "RateLimit",
    "RateLimitError",
    "ServerError",
    "ValidationError",
]
