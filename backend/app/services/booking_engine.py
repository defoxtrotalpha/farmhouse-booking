"""Booking engine — overlap detection for the approve flow.

Introduced in slice #23 (approve -> booked + overlap exclusion).
Reused by slice #24 (auto-reject losing pendings) and #26 (cancellation re-checks).

Overlap rule (app-level; SQLite serialises writers so this is race-safe):
  Two bookings on the SAME farmhouse_id conflict iff their BUFFERED ranges intersect.
  Buffered range of a booking B:
      [B.start_at - timedelta(minutes=B.buffer_minutes_snapshot),
       B.end_at   + timedelta(minutes=B.buffer_minutes_snapshot))   <- HALF-OPEN
  Intersection uses ranges_intersect (half-open, touching = NOT overlapping).
  ONLY status='booked' bookings are counted; holds/pendings are soft/competitive.
"""
from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from sqlalchemy.orm import Session

from app.services.availability import ranges_intersect


def find_booked_conflict(
    db: "Session",
    *,
    farmhouse_id: int,
    start_at: "datetime",
    end_at: "datetime",
    buffer_minutes: int,
    exclude_booking_id: int | None = None,
) -> "object | None":
    """Return the first status='booked' booking on farmhouse_id whose buffered
    range intersects the proposed booking's buffered range, or None if clear.

    Buffered range of the PROPOSED booking:
        my_start = start_at - timedelta(minutes=buffer_minutes)
        my_end   = end_at   + timedelta(minutes=buffer_minutes)

    Buffered range of each CANDIDATE booking c:
        c_start = c.start_at - timedelta(minutes=c.buffer_minutes_snapshot)
        c_end   = c.end_at   + timedelta(minutes=c.buffer_minutes_snapshot)

    Conflict iff: ranges_intersect(my_start, my_end, c_start, c_end)
        i.e. my_start < c_end  AND  c_start < my_end   (half-open STRICT)

    Parameters
    ----------
    db                  : active SQLAlchemy session
    farmhouse_id        : filter to this farmhouse only
    start_at / end_at   : UTC datetimes of the proposed booking
    buffer_minutes      : buffer for the proposed booking (snapshot value)
    exclude_booking_id  : skip this id (pass the booking's own id when
                          re-checking an existing booked booking)

    Returns
    -------
    First conflicting Booking row, or None.
    """
    from app.models.booking import Booking  # local import — avoids circular deps

    my_buf_start = start_at - timedelta(minutes=buffer_minutes)
    my_buf_end   = end_at   + timedelta(minutes=buffer_minutes)

    query = (
        db.query(Booking)
        .filter(
            Booking.farmhouse_id == farmhouse_id,
            Booking.status == "booked",
        )
    )
    if exclude_booking_id is not None:
        query = query.filter(Booking.id != exclude_booking_id)

    for candidate in query.all():
        buf = candidate.buffer_minutes_snapshot
        c_start = candidate.start_at - timedelta(minutes=buf)
        c_end   = candidate.end_at   + timedelta(minutes=buf)
        if ranges_intersect(my_buf_start, my_buf_end, c_start, c_end):
            return candidate

    return None
