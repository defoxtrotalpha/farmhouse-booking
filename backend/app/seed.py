"""Admin seed script.

Creates the initial admin user idempotently (safe to run multiple times).

Usage:
    python -m app.seed
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.security import hash_password


_DEFAULT_EMAIL = "admin@farmhouse.local"
_DEFAULT_PASSWORD = "admin12345"


def seed_admin(db: Session) -> None:
    """Create the admin user if it does not already exist."""
    from app.models.user import User  # local import avoids circular import at module level

    email = os.environ.get("SEED_ADMIN_EMAIL", _DEFAULT_EMAIL).lower().strip()
    password = os.environ.get("SEED_ADMIN_PASSWORD", _DEFAULT_PASSWORD)

    existing = db.query(User).filter_by(email=email).first()
    if existing:
        return

    admin = User(
        email=email,
        name="Admin",
        password_hash=hash_password(password),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()


if __name__ == "__main__":
    from app.db import SessionLocal
    import app.models  # noqa: F401 — ensure all models are registered

    db = SessionLocal()
    try:
        seed_admin(db)
        print("Admin seeded (or already exists).")
    finally:
        db.close()
