"""SQLAlchemy models package.

Import all model modules here so that ``Base.metadata`` is fully populated for
Alembic autogenerate and ``create_all`` in tests. Later slices append their
models and re-export them from this package.
"""
from __future__ import annotations

from app.db import Base
from app.models.user import User  # noqa: F401

__all__ = ["Base", "User"]
