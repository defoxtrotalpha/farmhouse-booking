"""Booking router — Hold a slot + Submit Pending (slice #22).

Endpoints
---------
POST /api/bookings/hold                 any active user  -> 201 BookingRead
POST /api/bookings/{booking_id}/submit  owner or admin   -> 200 BookingRead
GET  /api/bookings                      any active user  -> 200 [BookingRead]
GET  /api/bookings/{booking_id}         owner or admin   -> 200 BookingRead
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models.booking import Booking
from app.models.farmhouse import Farmhouse
from app.schemas.booking import BookingRead, HoldRequest, SubmitRequest
from app.services.activity import log_activity

router = APIRouter(prefix="/api", tags=["bookings"])

# ---------------------------------------------------------------------------
# Constants
# Slice #29 will source DEFAULT_HOLD_HOURS from the settings table.
# Until then, keep it here as a single named constant so it is easy to replace.
# ---------------------------------------------------------------------------
DEFAULT_HOLD_HOURS = 24


# ---------------------------------------------------------------------------
# POST /api/bookings/hold
# ---------------------------------------------------------------------------

@router.post("/bookings/hold", response_model=BookingRead, status_code=201)
def create_hold(
    body: HoldRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Booking:
    """Place a soft hold on a farmhouse slot.

    Validation order:
      1. start_at < end_at                    (422)
      2. start_at strictly in the future      (422)
      3. farmhouse exists                     (404)
      4. farmhouse status == 'active'         (400)
    Overlapping holds / pendings from other bookies are ALLOWED.
    """
    now = datetime.now(timezone.utc)

    # ── Normalise to UTC (accept any tz-aware ISO8601) ──────────────────────
    start_at = body.start_at
    end_at   = body.end_at
    if start_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_at must include timezone info")
    if end_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="end_at must include timezone info")
    start_at = start_at.astimezone(timezone.utc)
    end_at   = end_at.astimezone(timezone.utc)

    # ── Field validations ───────────────────────────────────────────────────
    if start_at >= end_at:
        raise HTTPException(status_code=422, detail="start_at must be strictly before end_at")
    if start_at <= now:
        raise HTTPException(status_code=422, detail="start_at must be in the future")

    # ── Farmhouse checks ────────────────────────────────────────────────────
    fh: Farmhouse | None = db.get(Farmhouse, body.farmhouse_id)
    if fh is None:
        raise HTTPException(status_code=404, detail="Farmhouse not found")
    if fh.status != "active":
        raise HTTPException(status_code=400, detail="Farmhouse is not active")

    # ── Create hold ─────────────────────────────────────────────────────────
    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=current_user.id,
        status="hold",
        start_at=start_at,
        end_at=end_at,
        buffer_minutes_snapshot=fh.buffer_minutes,
        expires_at=now + timedelta(hours=DEFAULT_HOLD_HOURS),
    )
    db.add(booking)
    db.flush()  # assigns booking.id before we log it

    log_activity(
        db,
        actor_id=current_user.id,
        action="hold.created",
        target_type="booking",
        target_id=booking.id,
    )
    db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# POST /api/bookings/{booking_id}/submit
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/submit", response_model=BookingRead)
def submit_booking(
    booking_id: int,
    body: SubmitRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Booking:
    """Attach client details to a hold and move it to 'pending'.

    Preconditions:
      - booking exists                              (404)
      - booking.status == 'hold'                    (409)
      - requester is owner (bookie_id) OR admin     (403)
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != "hold":
        raise HTTPException(status_code=409, detail="Booking is not in 'hold' status")
    if booking.bookie_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to submit this booking")

    # ── Attach client details ───────────────────────────────────────────────
    booking.client_name    = body.client_name
    booking.client_contact = body.client_contact
    booking.event_type     = body.event_type
    booking.event_info     = body.event_info
    booking.notes          = body.notes
    booking.quoted_price   = body.quoted_price
    booking.status         = "pending"
    booking.expires_at     = None  # pending bookings do not auto-expire

    log_activity(
        db,
        actor_id=current_user.id,
        action="request.submitted",
        target_type="booking",
        target_id=booking_id,
    )
    db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# GET /api/bookings
# ---------------------------------------------------------------------------

@router.get("/bookings", response_model=List[BookingRead])
def list_bookings(
    status: Optional[str] = Query(None, description="Filter by status"),
    farmhouse_id: Optional[int] = Query(None, description="Filter by farmhouse"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list:
    """List bookings.

    Bookie: sees only their own bookings (bookie_id == me).
    Admin:  sees all.
    Sorted newest first (created_at DESC).
    """
    query = db.query(Booking)

    if current_user.role != "admin":
        query = query.filter(Booking.bookie_id == current_user.id)
    if status is not None:
        query = query.filter(Booking.status == status)
    if farmhouse_id is not None:
        query = query.filter(Booking.farmhouse_id == farmhouse_id)

    return query.order_by(Booking.created_at.desc()).all()


# ---------------------------------------------------------------------------
# GET /api/bookings/{booking_id}
# ---------------------------------------------------------------------------

@router.get("/bookings/{booking_id}", response_model=BookingRead)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Booking:
    """Fetch a single booking.

    Only the owner (bookie_id) or an admin may view it.
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.bookie_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to view this booking")
    return booking
