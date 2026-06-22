"""InviteToken SQLAlchemy model.

Stores single-use, expiring invite tokens for the "invite a bookie" flow.
A token is invalid when:
  - used_at is not None  (already consumed), OR
  - expires_at < utcnow()  (expired).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TZDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InviteToken(Base):
    __tablename__ = "invite_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, default=_utcnow)

    @staticmethod
    def generate_token() -> str:
        """Return a URL-safe random token (43 chars, 256-bit entropy)."""
        return secrets.token_urlsafe(32)
