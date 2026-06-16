"""Unified error handling.

Raise `AppError` (or a subclass) anywhere; the registered handlers turn it — plus
request-validation errors and any unhandled exception — into the standard
`ApiResponse` envelope so every error looks the same to callers.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.responses import Blocker, failure

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Application error mapped to a unified API response + blocker."""

    http_status: int = 400
    status: str = "error"

    def __init__(
        self,
        message: str,
        *,
        code: str = "APP_ERROR",
        owner: str = "module2",
        field: str | None = None,
        http_status: int | None = None,
        status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.owner = owner
        self.field = field
        if http_status is not None:
            self.http_status = http_status
        if status is not None:
            self.status = status

    def to_blocker(self) -> Blocker:
        return Blocker(
            code=self.code, owner=self.owner, message=self.message, field=self.field
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        resp = failure(status=exc.status, blockers=[exc.to_blocker()])
        return JSONResponse(status_code=exc.http_status, content=resp.model_dump())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        blockers = [
            Blocker(
                code="VALIDATION_ERROR",
                owner="integration",
                field=".".join(str(p) for p in err["loc"]),
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        resp = failure(status="validation_failed", blockers=blockers)
        return JSONResponse(status_code=422, content=resp.model_dump())

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        detail = str(exc) if settings.debug else "Internal server error"
        resp = failure(
            status="internal_error",
            blockers=[Blocker(code="INTERNAL_ERROR", owner="module2", message=detail)],
        )
        return JSONResponse(status_code=500, content=resp.model_dump())
