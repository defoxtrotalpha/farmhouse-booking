"""Farmhouse CRUD router."""
from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.models.farmhouse import Farmhouse
from app.models.user import User
from app.schemas.farmhouse import FarmhouseCreate, FarmhouseRead, FarmhouseUpdate

router = APIRouter(prefix="/api", tags=["farmhouses"])

_VALID_STATUSES = {"active", "disabled"}


def _row_to_read(fh: Farmhouse) -> FarmhouseRead:
    """Convert ORM row -> FarmhouseRead, parsing operating_hours JSON if needed."""
    operating_hours = fh.operating_hours
    if isinstance(operating_hours, str):
        try:
            operating_hours = json.loads(operating_hours)
        except (json.JSONDecodeError, ValueError):
            pass  # return as-is
    return FarmhouseRead(
        id=fh.id,
        name=fh.name,
        description=fh.description,
        capacity=fh.capacity,
        buffer_minutes=fh.buffer_minutes,
        operating_hours=operating_hours,
        status=fh.status,
        created_at=fh.created_at,
        updated_at=fh.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/farmhouses
# ---------------------------------------------------------------------------

@router.get("/farmhouses", response_model=List[FarmhouseRead])
def list_farmhouses(
    include_disabled: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Farmhouse)
    # Bookies always get active-only; only admins can request all
    if current_user.role != "admin" or not include_disabled:
        query = query.filter(Farmhouse.status == "active")
    return [_row_to_read(fh) for fh in query.all()]


# ---------------------------------------------------------------------------
# GET /api/farmhouses/{id}
# ---------------------------------------------------------------------------

@router.get("/farmhouses/{farmhouse_id}", response_model=FarmhouseRead)
def get_farmhouse(
    farmhouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fh = db.query(Farmhouse).filter_by(id=farmhouse_id).first()
    if fh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farmhouse not found")
    return _row_to_read(fh)


# ---------------------------------------------------------------------------
# POST /api/farmhouses  (admin only)
# ---------------------------------------------------------------------------

@router.post("/farmhouses", response_model=FarmhouseRead, status_code=status.HTTP_201_CREATED)
def create_farmhouse(
    payload: FarmhouseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    operating_hours_text = (
        json.dumps(payload.operating_hours) if payload.operating_hours is not None else None
    )
    fh = Farmhouse(
        name=payload.name,
        description=payload.description,
        capacity=payload.capacity,
        buffer_minutes=payload.buffer_minutes,
        operating_hours=operating_hours_text,
    )
    db.add(fh)
    db.commit()
    db.refresh(fh)
    return _row_to_read(fh)


# ---------------------------------------------------------------------------
# PATCH /api/farmhouses/{id}  (admin only)
# ---------------------------------------------------------------------------

@router.patch("/farmhouses/{farmhouse_id}", response_model=FarmhouseRead)
def update_farmhouse(
    farmhouse_id: int,
    payload: FarmhouseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    fh = db.query(Farmhouse).filter_by(id=farmhouse_id).first()
    if fh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farmhouse not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "status" in update_data and update_data["status"] not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {_VALID_STATUSES}",
        )

    if "operating_hours" in update_data:
        oh = update_data.pop("operating_hours")
        fh.operating_hours = json.dumps(oh) if oh is not None else None

    for field, value in update_data.items():
        setattr(fh, field, value)

    db.commit()
    db.refresh(fh)
    return _row_to_read(fh)
