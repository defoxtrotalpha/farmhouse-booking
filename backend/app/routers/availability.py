"""Availability query endpoint.

GET /api/farmhouses/{farmhouse_id}/availability
  Query params : start (ISO8601 datetime), end (ISO8601 datetime)
  Auth required: any active user (get_current_user)
  Returns      : 200 list[AvailabilityEntry]
  Errors       : 401 unauthenticated, 404 farmhouse not found,
                 422 start >= end (business validation)

Intersection semantics: half-open [start, end).
  A booking intersects the window iff:
      booking.start_at < window_end  AND  booking.end_at > window_start
  This mirrors app.services.availability.ranges_intersect.
"""
from __future__ import annotations

from datetime import datetime, timezone as _tz
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models.farmhouse import Farmhouse
from app.models.user import User
from app.schemas.booking import AvailabilityEntry
from app.services.availability import get_occupied_bookings
from app.tenancy import tenant_clause

router = APIRouter(prefix="/api", tags=["availability"])


@router.get(
    "/farmhouses/{farmhouse_id}/availability",
    response_model=List[AvailabilityEntry],
)
def get_availability(
    farmhouse_id: int,
    start: datetime = Query(..., description="Window start (ISO8601, UTC)"),
    end: datetime = Query(..., description="Window end (ISO8601, UTC)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return occupied bookings (hold/pending/booked) that intersect [start, end)."""
    # Normalise to UTC-aware so TZDateTime bind-param conversion is deterministic
    if start.tzinfo is None:
        start = start.replace(tzinfo=_tz.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=_tz.utc)

    if start >= end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must be strictly before end",
        )

    fh = db.query(Farmhouse).filter(
        Farmhouse.id == farmhouse_id,
        tenant_clause(Farmhouse.tenant_id, current_user.tenant_id),
    ).first()
    if fh is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Farmhouse not found",
        )

    return get_occupied_bookings(db, farmhouse_id, start, end)
