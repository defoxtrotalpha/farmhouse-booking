"""BlackoutDate model — admin-managed date ranges that block new bookings.

farmhouse_id=NULL  -> global blackout (applies to all farmhouses)
farmhouse_id=<id>  -> applies only to that farmhouse

Dates are expressed in Asia/Karachi calendar terms (YYYY-MM-DD).
The booking-rules validator converts UTC booking times to local dates before
comparing against this table.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TZDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BlackoutDate(Base):
    __tablename__ = "blackout_dates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # NULL = global blackout applying to all farmhouses.
    farmhouse_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("farmhouses.id"), nullable=True, index=True
    )

    # Inclusive date range expressed in Asia/Karachi calendar dates.
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date:   Mapped[date] = mapped_column(Date, nullable=False)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, default=_utcnow)
