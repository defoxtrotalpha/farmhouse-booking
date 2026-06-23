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

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.models.activity import ActivityLog
from app.models.booking import Booking
from app.models.user import User
from app.schemas.activity import ActivityLogRead
from app.services.activity import log_activity
from app.tenancy import tenant_clause

router = APIRouter(prefix="/api", tags=["activity"])


@router.get("/activity", response_model=List[ActivityLogRead])
def list_activity(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ActivityLogRead]:
    """Return activity log entries for the user's company, filtered by role.

    Admin sees every entry in the company. A bookie sees entries they performed
    plus entries concerning their own bookings (e.g. an admin approving or
    rejecting their request).
    """
    q = db.query(ActivityLog).filter(
        tenant_clause(ActivityLog.tenant_id, current_user.tenant_id)
    )

    if current_user.role != "admin":
        my_booking_ids = db.query(Booking.id).filter(
            Booking.bookie_id == current_user.id
        )
        q = q.filter(
            or_(
                ActivityLog.actor_id == current_user.id,
                and_(
                    ActivityLog.target_type == "booking",
                    ActivityLog.target_id.in_(my_booking_ids),
                ),
            )
        )

    entries = (
        q.order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return entries


@router.delete("/activity", status_code=status.HTTP_204_NO_CONTENT)
def clear_activity(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Clear the admin's OWN activity log entries (admin only).

    Each admin can only clear the entries they performed — one admin can never
    wipe another admin's history.
    """
    db.query(ActivityLog).filter(
        tenant_clause(ActivityLog.tenant_id, admin.tenant_id),
        ActivityLog.actor_id == admin.id,
    ).delete(synchronize_session=False)
    log_activity(
        db,
        actor_id=admin.id,
        action="activity.cleared",
        target_type="user",
        target_id=admin.id,
        tenant_id=admin.tenant_id,
    )
    db.commit()
    return None
