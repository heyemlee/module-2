"""Environment / settings loading.

Single source of truth for configuration. Values come from environment variables
or a local `.env` file (see `.env.example`). Import `settings` anywhere.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- App ----
    app_name: str = "module2-production-engineering"
    environment: str = "development"
    debug: bool = True
    contract_version: str = "module2.v1"
    units: str = "inches"

    # ---- Server ----
    host: str = "0.0.0.0"
    port: int = 8000

    # ---- Database ----
    database_url: str = "sqlite:///./data/module2.db"

    # ---- CORS ----
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
