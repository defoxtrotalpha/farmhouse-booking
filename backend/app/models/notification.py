"""Notification SQLAlchemy model.

Introduced in slice #27 (in-app notification center).
One row per recipient per event — fan-out is done at write time.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TZDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ── recipient ─────────────────────────────────────────────────────────────
    recipient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    # ── event type / content ──────────────────────────────────────────────────
    # e.g. 'hold.created', 'request.submitted', 'booking.approved', ...
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── optional link to a booking ────────────────────────────────────────────
    booking_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bookings.id"), nullable=True
    )

    # ── read state ────────────────────────────────────────────────────────────
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )

    # ── audit ─────────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=_utcnow
    )
