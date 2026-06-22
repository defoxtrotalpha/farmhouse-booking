"""Notifications router.

Endpoints (all require an authenticated active user):

  GET  /api/notifications               list mine, newest first (default 50)
  GET  /api/notifications/unread-count  {"count": int}
  POST /api/notifications/read-all      mark all mine read -> {"updated": n}
  POST /api/notifications/{id}/read     mark one read (404 if not mine) -> NotificationRead

Note: /read-all and /unread-count are defined BEFORE /{id}/read so FastAPI
does not attempt to parse the literal path segments as integers.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models.notification import Notification
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/api", tags=["notifications"])


# ---------------------------------------------------------------------------
# GET /api/notifications
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=List[NotificationRead])
def list_notifications(
    unread: Optional[bool] = Query(None, description="If true return only unread; if false only read"),
    limit: int = Query(50, ge=1, le=200, description="Max results (1-200)"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list:
    """Return the current user's notifications, newest first."""
    q = db.query(Notification).filter(Notification.recipient_id == current_user.id)
    if unread is True:
        q = q.filter(Notification.is_read == False)  # noqa: E712
    elif unread is False:
        q = q.filter(Notification.is_read == True)   # noqa: E712
    return q.order_by(Notification.created_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# GET /api/notifications/unread-count  (must be before /{id}/read)
# ---------------------------------------------------------------------------

@router.get("/notifications/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Return the count of unread notifications for the current user."""
    count = (
        db.query(Notification)
        .filter(
            Notification.recipient_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .count()
    )
    return {"count": count}


# ---------------------------------------------------------------------------
# POST /api/notifications/read-all  (must be before /{id}/read)
# ---------------------------------------------------------------------------

@router.post("/notifications/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Mark all of the current user's unread notifications as read."""
    updated = (
        db.query(Notification)
        .filter(
            Notification.recipient_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .update({"is_read": True})
    )
    db.commit()
    return {"updated": updated}


# ---------------------------------------------------------------------------
# POST /api/notifications/{notification_id}/read
# ---------------------------------------------------------------------------

@router.post("/notifications/{notification_id}/read", response_model=NotificationRead)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Notification:
    """Mark a single notification read.  404 if it doesn't belong to the caller."""
    n: Notification | None = db.get(Notification, notification_id)
    if n is None or n.recipient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n
