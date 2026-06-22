"""Application configuration.

All timestamps are stored in UTC. The business timezone (Asia/Karachi) is used
only for display/conversion at the edges. SQLite is the v1 local datastore; the
data layer is kept DB-agnostic via SQLAlchemy so PostgreSQL remains a later option.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage (v1: local SQLite file).
    database_url: str = "sqlite:///./booking.db"

    # Business timezone for display. Storage is always UTC.
    business_timezone: str = "Asia/Karachi"

    # Auth (used by later slices).
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14

    # CORS origins for the Vite dev server.
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
