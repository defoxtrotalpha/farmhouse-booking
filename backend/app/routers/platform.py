"""Platform administration router — global-admin only.

Global admins govern the whole deployment (they have ``tenant_id IS NULL``):

  Companies
    GET    /api/companies                 -> list all companies + admin + counts
    POST   /api/companies                 -> create an approved company + its admin
    POST   /api/companies/{id}/approve    -> approve a pending company
    POST   /api/companies/{id}/reject     -> reject a pending company
    DELETE /api/companies/{id}            -> remove a company and all its data

  Global admins
    GET    /api/global-admins             -> list all global admins
    POST   /api/global-admins             -> add another global admin
    DELETE /api/global-admins/{id}        -> remove a global admin (>=1 must remain)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_global_admin
from app.models.activity import ActivityLog
from app.models.blackout import BlackoutDate
from app.models.booking import Booking
from app.models.farmhouse import Farmhouse
from app.models.invite import InviteToken
from app.models.notification import Notification
from app.models.policy import Policy
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.platform import (
    CompanyCreateRequest,
    CompanyRead,
    GlobalAdminCreateRequest,
    GlobalAdminRead,
)
from app.security import hash_password
from app.services.activity import log_activity
from app.tenancy import slugify

router = APIRouter(prefix="/api", tags=["platform"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _company_to_read(db: Session, t: Tenant) -> CompanyRead:
    members = db.query(User).filter(User.tenant_id == t.id).all()
    admins = [u for u in members if u.role == "admin"]
    # The primary admin is the lowest-id admin in the company.
    primary = min(admins, key=lambda u: u.id) if admins else None
    fh_count = db.query(Farmhouse).filter(Farmhouse.tenant_id == t.id).count()
    return CompanyRead(
        id=t.id,
        name=t.name,
        slug=t.slug,
        status=t.status,
        created_at=t.created_at,
        admin_name=primary.name if primary else None,
        admin_email=primary.email if primary else None,
        admin_count=len(admins),
        member_count=len(members),
        farmhouse_count=fh_count,
    )


def _unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    n = 2
    while db.query(Tenant).filter(Tenant.slug == slug).first() is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

@router.get("/companies", response_model=list[CompanyRead])
def list_companies(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_global_admin),
):
    """List every company on the platform, newest first."""
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [_company_to_read(db, t) for t in tenants]


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_global_admin),
):
    """Create an approved company together with its first (active) admin."""
    company_name = (body.company_name or "").strip()
    email = (body.admin_email or "").lower().strip()
    if not company_name:
        raise HTTPException(status_code=422, detail="Company name is required")
    if not email:
        raise HTTPException(status_code=422, detail="Admin email is required")
    if len(body.admin_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    tenant = Tenant(name=company_name, slug=_unique_slug(db, company_name), status="approved")
    db.add(tenant)
    db.flush()

    new_admin = User(
        tenant_id=tenant.id,
        email=email,
        username=None,
        name=(body.admin_name or "Admin").strip() or "Admin",
        password_hash=hash_password(body.admin_password),
        role="admin",
        is_active=True,
    )
    db.add(new_admin)
    db.flush()

    log_activity(
        db,
        actor_id=admin.id,
        action="company.created",
        target_type="tenant",
        target_id=tenant.id,
        tenant_id=tenant.id,
    )
    db.commit()
    return _company_to_read(db, tenant)


@router.post("/companies/{tenant_id}/approve", response_model=CompanyRead)
def approve_company(
    tenant_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_global_admin),
):
    """Approve a pending company and activate its admin accounts."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    tenant.status = "approved"
    # Activate the company's admins so they can sign in.
    for u in db.query(User).filter(User.tenant_id == tenant.id, User.role == "admin").all():
        u.is_active = True
    log_activity(
        db,
        actor_id=admin.id,
        action="company.approved",
        target_type="tenant",
        target_id=tenant.id,
        tenant_id=tenant.id,
    )
    db.commit()
    return _company_to_read(db, tenant)


@router.post("/companies/{tenant_id}/reject", response_model=CompanyRead)
def reject_company(
    tenant_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_global_admin),
):
    """Reject a company; its members remain unable to sign in."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    tenant.status = "rejected"
    for u in db.query(User).filter(User.tenant_id == tenant.id).all():
        u.is_active = False
    log_activity(
        db,
        actor_id=admin.id,
        action="company.rejected",
        target_type="tenant",
        target_id=tenant.id,
        tenant_id=tenant.id,
    )
    db.commit()
    return _company_to_read(db, tenant)


@router.delete("/companies/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    tenant_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_global_admin),
):
    """Permanently remove a company and all of its data."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    user_ids = [u.id for u in db.query(User.id).filter(User.tenant_id == tenant.id).all()]
    if user_ids:
        db.query(Notification).filter(Notification.recipient_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(InviteToken).filter(InviteToken.user_id.in_(user_ids)).delete(synchronize_session=False)

    db.query(ActivityLog).filter(ActivityLog.tenant_id == tenant.id).delete(synchronize_session=False)
    db.query(Booking).filter(Booking.tenant_id == tenant.id).delete(synchronize_session=False)
    db.query(BlackoutDate).filter(BlackoutDate.tenant_id == tenant.id).delete(synchronize_session=False)
    db.query(Policy).filter(Policy.tenant_id == tenant.id).delete(synchronize_session=False)
    db.query(Farmhouse).filter(Farmhouse.tenant_id == tenant.id).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id == tenant.id).delete(synchronize_session=False)
    db.delete(tenant)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Global admins
# ---------------------------------------------------------------------------

def _global_admin_to_read(u: User) -> GlobalAdminRead:
    return GlobalAdminRead(id=u.id, name=u.name, email=u.email, created_at=u.created_at)


@router.get("/global-admins", response_model=list[GlobalAdminRead])
def list_global_admins(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_global_admin),
):
    """List all platform global admins, newest first."""
    admins = (
        db.query(User)
        .filter(User.role == "global_admin")
        .order_by(User.created_at.desc())
        .all()
    )
    return [_global_admin_to_read(u) for u in admins]


@router.post("/global-admins", response_model=GlobalAdminRead, status_code=status.HTTP_201_CREATED)
def create_global_admin(
    body: GlobalAdminCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_global_admin),
):
    """Add another global admin."""
    email = (body.email or "").lower().strip()
    if not email:
        raise HTTPException(status_code=422, detail="Email is required")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    new_admin = User(
        tenant_id=None,
        email=email,
        username=None,
        name=(body.name or "Global Admin").strip() or "Global Admin",
        password_hash=hash_password(body.password),
        role="global_admin",
        is_active=True,
    )
    db.add(new_admin)
    db.flush()
    log_activity(
        db,
        actor_id=admin.id,
        action="global_admin.added",
        target_type="user",
        target_id=new_admin.id,
    )
    db.commit()
    return _global_admin_to_read(new_admin)


@router.delete("/global-admins/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_global_admin),
):
    """Remove a global admin. At least one global admin must always remain."""
    target = db.get(User, user_id)
    if target is None or target.role != "global_admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global admin not found")

    remaining = db.query(User).filter(User.role == "global_admin").count()
    if remaining <= 1:
        raise HTTPException(status_code=400, detail="At least one global admin must remain")

    db.query(ActivityLog).filter(ActivityLog.actor_id == target.id).update(
        {ActivityLog.actor_id: None}, synchronize_session=False
    )
    db.delete(target)
    log_activity(
        db,
        actor_id=admin.id,
        action="global_admin.removed",
        target_type="user",
        target_id=user_id,
    )
    db.commit()
    return None
