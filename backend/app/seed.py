"""Platform seed script.

Creates the initial *global admin* idempotently (safe to run multiple times).
A global admin governs the whole deployment: it has no company
(``tenant_id IS NULL``) and manages companies and other global admins.

No demo company is created — companies are added by the global admin (or via
the public "create your company" request, pending approval).

Usage:
    python -m app.seed
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.security import hash_password


_DEFAULT_EMAIL = "admin@farmhouse.com"
_DEFAULT_PASSWORD = "admin12345"


def seed_admin(db: Session) -> None:
    """Create the default global admin if one does not already exist."""
    from app.models.user import User  # local import avoids circular import

    email = os.environ.get("SEED_ADMIN_EMAIL", _DEFAULT_EMAIL).lower().strip()
    password = os.environ.get("SEED_ADMIN_PASSWORD", _DEFAULT_PASSWORD)

    existing = db.query(User).filter_by(email=email).first()
    if existing:
        # Ensure the seeded account is a proper global admin.
        existing.role = "global_admin"
        existing.tenant_id = None
        existing.is_active = True
        db.commit()
        return

    admin = User(
        tenant_id=None,
        email=email,
        username=None,
        name="Global Admin",
        password_hash=hash_password(password),
        role="global_admin",
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
        print("Global admin seeded (or already exists).")
    finally:
        db.close()
