"""Hold-expiry service.

Provides:
  - is_hold_expired(booking, now) -> bool
    Pure predicate; no DB access.
  - expire_stale_holds(db, now=None) -> int
    Batch-sweeps status='hold' rows whose expires_at < now, flips them to
    'expired', commits, and returns the count of rows changed.
    Used directly by the APScheduler job and directly unit-testable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def is_hold_expired(booking, now: datetime) -> bool:
    """Return True iff the booking is a hold that has passed its expiry time.

    A booking qualifies only when:
      - status == 'hold'   (pending/booked/etc. with old expires_at do NOT count)
      - expires_at is not None
      - expires_at < now   (strictly before — equal is still live)
    """
    return (
        booking.status == "hold"
        and booking.expires_at is not None
        and booking.expires_at < now
    )


def expire_stale_holds(db: "Session", now: datetime | None = None) -> int:
    """Flip all stale holds to 'expired'.

    A hold is stale when:
      - status == 'hold'
      - expires_at is not None
      - expires_at < now

    Commits the transaction and returns the number of rows changed.
    If *now* is omitted it defaults to ``datetime.now(timezone.utc)``.

    This function is the body of the APScheduler cleanup job and is also
    called directly in tests (no live scheduler needed).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    from app.models.booking import Booking  # local import avoids circular deps

    stale = (
        db.query(Booking)
        .filter(
            Booking.status == "hold",
            Booking.expires_at.isnot(None),
            Booking.expires_at < now,
        )
        .all()
    )
    for b in stale:
        b.status = "expired"
    db.commit()
    return len(stale)
