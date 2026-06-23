"""Users router — admin management of bookies/admins.

Routes:
  GET   /api/users           (require_admin) -> [UserRead]
  PATCH /api/users/{user_id} (require_admin) -> UserRead  (enable/disable)

Surfaces the roster of invited bookies along with whether each has accepted
their invite (set a password). Resolves the Issues.md gap: "in my bookings, I
do not see all bookies that I have added and whether they have accepted the
invite or not".
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.models.activity import ActivityLog
from app.models.booking import Booking
from app.models.invite import InviteToken
from app.models.notification import Notification
from app.models.user import User
from app.schemas.user import DirectUserCreate, UserRead, UserUpdate
from app.security import hash_password
from app.services.activity import log_activity
from app.tenancy import tenant_clause

router = APIRouter(prefix="/api", tags=["users"])


def _primary_admin_id(db: Session, tenant_id) -> int | None:
    """The founding admin of a tenant = the lowest-id active admin account.

    This account is protected: it can never be removed or disabled.
    """
    return (
        db.query(func.min(User.id))
        .filter(tenant_clause(User.tenant_id, tenant_id), User.role == "admin")
        .scalar()
    )


def _to_read(u: User, primary_id: int | None = None) -> UserRead:
    return UserRead(
        id=u.id,
        name=u.name,
        email=u.email,
        username=u.username,
        role=u.role,
        is_active=u.is_active,
        accepted=u.password_hash is not None,
        is_primary=(primary_id is not None and u.id == primary_id),
        created_at=u.created_at,
    )


@router.get("/users", response_model=List[UserRead])
def list_users(
    role: Optional[str] = Query(None, description="Filter by role (e.g. 'bookie')"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list:
    """List users in the caller's company. Any authenticated user may view the
    roster (so bookies can see admins and fellow bookies); only admins can
    mutate it via the other endpoints."""
    query = db.query(User).filter(tenant_clause(User.tenant_id, current_user.tenant_id))
    if role is not None:
        query = query.filter(User.role == role)
    users = query.order_by(User.created_at.desc()).all()
    primary_id = _primary_admin_id(db, current_user.tenant_id)
    return [_to_read(u, primary_id) for u in users]


@router.post("/users/direct", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user_direct(
    body: DirectUserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserRead:
    """Admin creates an active user with username + password (no invite needed)."""
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=422, detail="Username is required")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    role = body.role if body.role in ("bookie", "admin") else "bookie"

    if db.query(User).filter(User.username == username).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    email = body.email.lower().strip() if body.email else None
    if email and db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        tenant_id=admin.tenant_id,
        email=email,
        username=username,
        name=body.name or username,
        password_hash=hash_password(body.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    log_activity(
        db,
        actor_id=admin.id,
        action="user.created",
        target_type="user",
        target_id=user.id,
        note=f"direct add ({role})",
    )
    db.commit()
    db.refresh(user)
    return _to_read(user)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserRead:
    """Enable or disable a user (admin only). Admins cannot disable themselves."""
    user: User | None = db.get(User, user_id)
    if user is None or not _same_tenant(user, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.is_active is not None:
        if user.id == admin.id and body.is_active is False:
            raise HTTPException(status_code=400, detail="You cannot disable your own account")
        if body.is_active is False and user.id == _primary_admin_id(db, admin.tenant_id):
            raise HTTPException(status_code=400, detail="The primary admin account cannot be disabled")
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)
    return _to_read(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Permanently remove a user and their bookings/notifications/invites (admin only)."""
    user: User | None = db.get(User, user_id)
    if user is None or not _same_tenant(user, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot remove your own account")
    if user.id == _primary_admin_id(db, admin.tenant_id):
        raise HTTPException(status_code=400, detail="The primary admin account cannot be removed")

    # Detach the actor from any activity entries (audit history is preserved).
    db.query(ActivityLog).filter(ActivityLog.actor_id == user.id).update(
        {ActivityLog.actor_id: None}, synchronize_session=False
    )
    db.query(Notification).filter(Notification.recipient_id == user.id).delete(
        synchronize_session=False
    )
    db.query(InviteToken).filter(InviteToken.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(Booking).filter(Booking.bookie_id == user.id).delete(
        synchronize_session=False
    )
    log_activity(
        db,
        actor_id=admin.id,
        action="user.removed",
        target_type="user",
        target_id=user.id,
        note=user.username or user.email or user.name,
        tenant_id=admin.tenant_id,
    )
    db.delete(user)
    db.commit()
    return None


def _same_tenant(user: User, admin: User) -> bool:
    return user.tenant_id == admin.tenant_id
