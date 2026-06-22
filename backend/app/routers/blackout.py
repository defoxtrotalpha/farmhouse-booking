"""Blackout dates router — slice #29.

GET    /api/blackouts                  any active user   -> 200 [BlackoutRead]
POST   /api/blackouts                  admin only        -> 201 BlackoutRead
DELETE /api/blackouts/{blackout_id}    admin only        -> 204
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.models.blackout import BlackoutDate
from app.schemas.blackout import BlackoutCreate, BlackoutRead
from app.services.activity import log_activity

router = APIRouter(prefix="/api", tags=["blackouts"])


# ---------------------------------------------------------------------------
# GET /api/blackouts
# ---------------------------------------------------------------------------

@router.get("/blackouts", response_model=List[BlackoutRead])
def list_blackouts(
    farmhouse_id: Optional[int] = Query(None, description="Filter: include global + this farmhouse only"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List blackout dates.

    Without ?farmhouse_id=, returns all blackouts.
    With ?farmhouse_id=X, returns only global (farmhouse_id IS NULL) blackouts
    plus those assigned specifically to farmhouse X.
    """
    query = db.query(BlackoutDate)
    if farmhouse_id is not None:
        query = query.filter(
            or_(
                BlackoutDate.farmhouse_id.is_(None),
                BlackoutDate.farmhouse_id == farmhouse_id,
            )
        )
    return query.order_by(BlackoutDate.start_date).all()


# ---------------------------------------------------------------------------
# POST /api/blackouts
# ---------------------------------------------------------------------------

@router.post("/blackouts", response_model=BlackoutRead, status_code=201)
def create_blackout(
    body: BlackoutCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Create a blackout date range. Admin only."""
    if body.start_date > body.end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date",
        )

    b = BlackoutDate(
        farmhouse_id=body.farmhouse_id,
        start_date=body.start_date,
        end_date=body.end_date,
        reason=body.reason,
    )
    db.add(b)
    db.flush()  # assigns b.id before logging

    log_activity(
        db,
        actor_id=current_user.id,
        action="blackout.created",
        target_type="blackout_date",
        target_id=b.id,
    )
    db.commit()
    db.refresh(b)
    return b


# ---------------------------------------------------------------------------
# DELETE /api/blackouts/{blackout_id}
# ---------------------------------------------------------------------------

@router.delete("/blackouts/{blackout_id}", status_code=204)
def delete_blackout(
    blackout_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Delete a blackout date. Admin only."""
    b = db.get(BlackoutDate, blackout_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Blackout not found")

    log_activity(
        db,
        actor_id=current_user.id,
        action="blackout.deleted",
        target_type="blackout_date",
        target_id=blackout_id,
    )
    db.delete(b)
    db.commit()
    return Response(status_code=204)
