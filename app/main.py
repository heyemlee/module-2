"""FastAPI entrypoint (infra scaffold only — no business routes yet).

Wires settings, DB init on startup, CORS, unified error handlers, and meta routes
(`/` and `/health`). Business endpoints (production-packages) are added later.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.config import settings
from app.db import init_db
from app.errors import register_exception_handlers
from app.responses import ApiResponse, success
from app.routes import router as module2_router

_STATIC = Path(__file__).parent / "static"
_DEMO_PATH = _STATIC / "demo.html"
_CONSOLE_PATH = _STATIC / "test_console.html"

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Module 2 - Production Engineering Engine",
        version=settings.contract_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(module2_router)

    @app.get("/", response_class=HTMLResponse, tags=["meta"])
    def root() -> HTMLResponse:
        """Module 1 -> Module 2 demo: rough cabinets -> complete -> panels + cut sheet."""
        return HTMLResponse(_DEMO_PATH.read_text(encoding="utf-8"))

    @app.get("/console", response_class=HTMLResponse, tags=["meta"])
    def console() -> HTMLResponse:
        """Raw JSON test console for power users / debugging."""
        return HTMLResponse(_CONSOLE_PATH.read_text(encoding="utf-8"))

    @app.get("/health", response_model=ApiResponse, tags=["meta"])
    def health() -> ApiResponse:
        return success(
            status="ok",
            data={"service": settings.app_name, "environment": settings.environment},
        )

    return app


app = create_app()
