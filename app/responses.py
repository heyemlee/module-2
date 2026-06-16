"""Unified API response envelope.

Every response carries `ok`, `status`, `contract_version`, and `blockers` — matching
the Module 2 API contract. `data` holds the endpoint-specific payload.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.config import settings


class Blocker(BaseModel):
    """A reason something cannot proceed. `owner` decides who must fix it."""

    code: str
    owner: str  # module1 | module2 | module3 | integration
    message: str
    field: str | None = None


class ApiResponse(BaseModel):
    ok: bool
    status: str
    contract_version: str = Field(default_factory=lambda: settings.contract_version)
    data: dict[str, Any] | None = None
    blockers: list[Blocker] = Field(default_factory=list)


def success(status: str, data: dict[str, Any] | None = None) -> ApiResponse:
    return ApiResponse(ok=True, status=status, data=data, blockers=[])


def failure(status: str, blockers: list[Blocker]) -> ApiResponse:
    return ApiResponse(ok=False, status=status, data=None, blockers=blockers)
