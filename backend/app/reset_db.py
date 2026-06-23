"""Reset the local development database.

Drops every table and recreates the schema directly from the current models
(via ``Base.metadata.create_all``), then seeds the default company + admin.

This is intended for LOCAL development only — it destroys all data. Production
schema management is handled by Alembic migrations.

Usage:
    python -m app.reset_db
"""
from __future__ import annotations

from app.db import Base, SessionLocal, engine
import app.models  # noqa: F401 — registers every model with Base.metadata
from app.seed import seed_admin


def reset() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_admin(db)
    finally:
        db.close()


if __name__ == "__main__":
    reset()
    print("Database reset and seeded (global admin admin@farmhouse.com).")
