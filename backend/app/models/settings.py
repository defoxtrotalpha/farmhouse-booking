"""SystemSettings model — DB-backed singleton (id=1) for runtime configuration.

This row overrides the env-default values in app/config.py at runtime.
Slice #29: hold_duration_hours, min_advance_notice_minutes,
           default_buffer_minutes, operating_hours_start/end.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, TZDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Hold duration (hours). Sourced here; overrides env Settings.hold_duration_hours.
    hold_duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)

    # Minimum advance notice before booking start (minutes). 0 = OFF (no check).
    min_advance_notice_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Default buffer between bookings (minutes). Applied when farmhouse has no
    # per-farmhouse buffer set. Currently informational; future versions may use
    # this as the global fallback in the booking engine.
    default_buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Global operating hours window (HH:MM, Asia/Karachi local time).
    # NULL means no global operating-hours constraint.
    # Per-farmhouse operating_hours takes precedence when set.
    operating_hours_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    operating_hours_end:   Mapped[str | None] = mapped_column(String(5), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


def get_or_create_settings(db: Session) -> SystemSettings:
    """Return the singleton settings row (id=1), creating it with defaults if absent.

    If the row does not yet exist, it is inserted and committed immediately so
    that subsequent read-only requests (GET /api/settings) also find the row.
    The caller may still update the returned instance and commit again.
    """
    s = db.get(SystemSettings, 1)
    if s is None:
        s = SystemSettings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s
