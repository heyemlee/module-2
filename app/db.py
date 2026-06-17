"""Database connection (SQLAlchemy 2.0).

MVP uses SQLite. Switching to Postgres later only requires changing DATABASE_URL.
ORM models inherit from `Base`; `init_db()` creates tables on startup; `get_db()`
is the FastAPI dependency that yields a session and always closes it.
"""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


# SQLite + FastAPI threadpool needs check_same_thread=False.
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    echo=settings.debug,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create the SQLite data directory (if any) and all known tables."""
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.replace("sqlite:///", "", 1)
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    # Import ORM models so their tables register on Base.metadata before create_all.
    from app import store  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a DB session, always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
