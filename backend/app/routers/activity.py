"""Activity Log router.

Routes (all read-only — the log is APPEND-ONLY):
  GET /api/activity   (auth required)  -> list[ActivityLogRead]

Role-filter rule
----------------
* Admin  : sees ALL entries, newest-first, paginated.
* Bookie : sees only entries where actor_id == their own user id.

EXTENSION POINT (booking ownership)
------------------------------------
When the Bookings slice is implemented, the bookie filter should be expanded
to also include booking-related entries that concern the bookie's own bookings,
even if actor_id != bookie.id (e.g. admin approves bookie's booking).
Search for the comment "# BOOKING-OWNERSHIP EXTENSION POINT" below and add:

    from sqlalchemy import or_
    # from app.models.booking import Booking  (import when available)
    # booking_target_ids = db.query(Booking.id).filter_by(created_by=current_user.id)
    # q = q.filter(
    #     or_(
    #         ActivityLog.actor_id == current_user.id,
    #         and_(
    #             ActivityLog.target_type == "booking",
    #             ActivityLog.target_id.in_(booking_target_ids),
    #         ),
    #     )
    # )
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models.activity import ActivityLog
from app.models.user import User
from app.schemas.activity import ActivityLogRead

router = APIRouter(prefix="/api", tags=["activity"])


@router.get("/activity", response_model=List[ActivityLogRead])
def list_activity(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ActivityLogRead]:
    """Return activity log entries filtered by role.

    Admin sees all; bookie sees only their own entries.
    See module docstring for the booking-ownership extension point.
    """
    q = db.query(ActivityLog)

    if current_user.role != "admin":
        # BOOKING-OWNERSHIP EXTENSION POINT — see module docstring above
        q = q.filter(ActivityLog.actor_id == current_user.id)

    entries = (
        q.order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return entries
