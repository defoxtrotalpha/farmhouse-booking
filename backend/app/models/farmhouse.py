"""Farmhouse SQLAlchemy model."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TZDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Farmhouse(Base):
    __tablename__ = "farmhouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # operating_hours stored as JSON text, e.g. '{"mon":["09:00","23:00"], ...}' or NULL
    operating_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )
