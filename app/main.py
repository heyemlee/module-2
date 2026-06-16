"""FastAPI entrypoint (infra scaffold only — no business routes yet).

Wires settings, DB init on startup, CORS, unified error handlers, and meta routes
(`/` and `/health`). Business endpoints (production-packages) are added later.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.errors import register_exception_handlers
from app.responses import ApiResponse, success

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

    @app.get("/", response_model=ApiResponse, tags=["meta"])
    def root() -> ApiResponse:
        return success(
            status="ok",
            data={
                "service": settings.app_name,
                "contract_version": settings.contract_version,
                "docs": "/docs",
            },
        )

    @app.get("/health", response_model=ApiResponse, tags=["meta"])
    def health() -> ApiResponse:
        return success(
            status="ok",
            data={"service": settings.app_name, "environment": settings.environment},
        )

    return app


app = create_app()
