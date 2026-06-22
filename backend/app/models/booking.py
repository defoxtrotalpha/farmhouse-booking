"""Booking SQLAlchemy model.

Introduced in slice #21 (read-only calendar / availability).
Later slices add hold/submit/approve/reject/cancel logic on top of this model.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TZDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ── foreign keys ──────────────────────────────────────────────────────────
    farmhouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("farmhouses.id"), nullable=False, index=True
    )
    bookie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    # ── core booking fields ───────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # allowed values: 'hold' | 'pending' | 'booked' | 'rejected' | 'canceled' | 'expired'

    start_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    # arbitrary range — MAY span midnight / multiple days

    buffer_minutes_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # ── optional client / event detail (filled when submitting → pending) ─────
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    quoted_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── hold expiry ───────────────────────────────────────────────────────────
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    # ── approval / rejection / cancellation ──────────────────────────────────
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── cancellation request (slice #26) ─────────────────────────────────────
    # Set when a bookie requests cancellation of their own BOOKED event (does
    # NOT change status — stays 'booked' until admin confirms).
    cancel_requested_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    cancel_requested_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # Reason supplied with a cancel request or an admin cancel.
    # (existing `reason` column is for reject; `cancel_reason` is for cancellation.)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )
