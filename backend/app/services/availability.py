"""Pure availability helpers — unit-testable independent of HTTP.

Intersection semantics: HALF-OPEN intervals [start, end).
  ranges_intersect(a_start, a_end, b_start, b_end) -> bool
  Two half-open intervals intersect iff: a_start < b_end AND b_start < a_end.
  Adjacent intervals (a_end == b_start) are NOT considered overlapping.

Later slices (hold/approve) also import get_occupied_bookings and the
buffered variant for the exclusive-booked overlap check.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_OCCUPIED_STATUSES = ("hold", "pending", "booked")


def ranges_intersect(
    a_start: datetime,
    a_end: datetime,
    b_start: datetime,
    b_end: datetime,
) -> bool:
    """Return True when half-open intervals [a_start, a_end) and [b_start, b_end) overlap.

    Half-open semantics: touching at a boundary (a_end == b_start) is NOT an
    intersection.  Condition: a_start < b_end AND b_start < a_end.
    """
    return a_start < b_end and b_start < a_end


def get_occupied_bookings(
    db: "Session",
    farmhouse_id: int,
    window_start: datetime,
    window_end: datetime,
) -> list:
    """Return Booking rows with status in (hold, pending, booked) that intersect
    the half-open query window [window_start, window_end).

    The SQL filter mirrors ranges_intersect:
        booking.start_at < window_end  AND  booking.end_at > window_start
    which is equivalent to ranges_intersect(booking.start_at, booking.end_at,
                                           window_start, window_end).
    """
    from app.models.booking import Booking  # local import avoids circular deps

    return (
        db.query(Booking)
        .filter(
            Booking.farmhouse_id == farmhouse_id,
            Booking.status.in_(_OCCUPIED_STATUSES),
            Booking.start_at < window_end,
            Booking.end_at > window_start,
        )
        .all()
    )
