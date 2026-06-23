"""Policy / Terms management router."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.models.policy import Policy
from app.models.user import User
from app.schemas.policy import PolicyCreate, PolicyRead, PolicyUpdate
from app.services.activity import log_activity
from app.tenancy import tenant_clause

router = APIRouter(prefix="/api", tags=["policies"])


# ---------------------------------------------------------------------------
# GET /api/policies  (any authenticated user)
# ---------------------------------------------------------------------------

@router.get("/policies", response_model=List[PolicyRead])
def list_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Policy).filter(
        tenant_clause(Policy.tenant_id, current_user.tenant_id)
    ).order_by(Policy.id).all()


# ---------------------------------------------------------------------------
# GET /api/policies/{id}  (any authenticated user)
# ---------------------------------------------------------------------------

@router.get("/policies/{policy_id}", response_model=PolicyRead)
def get_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    policy = db.query(Policy).filter(
        Policy.id == policy_id,
        tenant_clause(Policy.tenant_id, current_user.tenant_id),
    ).first()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


# ---------------------------------------------------------------------------
# POST /api/policies  (admin only) — create with version=1
# ---------------------------------------------------------------------------

@router.post("/policies", response_model=PolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    policy = Policy(
        tenant_id=current_user.tenant_id,
        title=payload.title,
        body=payload.body,
        version=1,
    )
    db.add(policy)
    db.flush()  # assign id before activity log
    log_activity(
        db,
        actor_id=current_user.id,
        action="policy.created",
        target_type="policy",
        target_id=policy.id,
    )
    db.commit()
    db.refresh(policy)
    return policy


# ---------------------------------------------------------------------------
# PATCH /api/policies/{id}  (admin only) — partial edit, bumps version
# ---------------------------------------------------------------------------

@router.patch("/policies/{policy_id}", response_model=PolicyRead)
def update_policy(
    policy_id: int,
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    policy = db.query(Policy).filter(
        Policy.id == policy_id,
        tenant_clause(Policy.tenant_id, current_user.tenant_id),
    ).first()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

    if payload.title is not None:
        policy.title = payload.title
    if payload.body is not None:
        policy.body = payload.body
    policy.version = policy.version + 1

    db.flush()
    log_activity(
        db,
        actor_id=current_user.id,
        action="policy.updated",
        target_type="policy",
        target_id=policy.id,
    )
    db.commit()
    db.refresh(policy)
    return policy
