"""Booking router — Hold / Submit / Approve + list/get.

Endpoints
---------
POST /api/bookings/hold                  any active user  -> 201 BookingRead
POST /api/bookings/{booking_id}/submit   owner or admin   -> 200 BookingRead
POST /api/bookings/{booking_id}/approve  admin only       -> 200 BookingRead
GET  /api/bookings                       any active user  -> 200 [BookingRead]
GET  /api/bookings/{booking_id}          owner or admin   -> 200 BookingRead
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_, not_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.models.booking import Booking
from app.models.farmhouse import Farmhouse
from app.models.settings import get_or_create_settings
from app.models.user import User
from app.schemas.booking import (
    BookingRead, HoldRequest, SubmitRequest,
    RejectRequest, RejectBatchRequest, RejectBatchResponse,
    CancelRequest, WithdrawRequest, RequestCancelBody,
    DirectBookRequest,
)
from app.services.activity import log_activity
from app.services.booking_engine import find_booked_conflict, find_overlapping_unresolved
from app.services.booking_rules import validate_booking_window
from app.services.hold_expiry import is_hold_expired
from app.services.notifications import dispatch_booking_event

router = APIRouter(prefix="/api", tags=["bookings"])

# Serializes the approve check-and-commit critical section. SQLite serialises
# writers but NOT the read-then-write (write-skew): two concurrent approvals
# could both pass the conflict SELECT before either commits. For the
# single-process v1 deployment this process-level lock guarantees that the
# overlap check and the booked-write are atomic, so confirmed double bookings
# are impossible. (If ever scaled to multiple processes, replace with a DB-level
# guard such as Postgres' EXCLUDE constraint or SELECT ... FOR UPDATE.)
_approve_lock = threading.Lock()


def _enrich(db: Session, bookings: list[Booking]) -> list[Booking]:
    """Attach farmhouse_name + bookie_name to each booking for display.

    These are non-mapped attributes set directly on the ORM instances; Pydantic
    (from_attributes=True) reads them via getattr when building BookingRead.
    Batch-loads names to avoid N+1 queries.
    """
    if not bookings:
        return bookings
    fh_ids = {b.farmhouse_id for b in bookings}
    user_ids = {b.bookie_id for b in bookings}
    fh_names = {
        fh.id: fh.name
        for fh in db.query(Farmhouse.id, Farmhouse.name).filter(Farmhouse.id.in_(fh_ids)).all()
    }
    user_names = {
        u.id: (u.name or u.email)
        for u in db.query(User.id, User.name, User.email).filter(User.id.in_(user_ids)).all()
    }
    for b in bookings:
        b.farmhouse_name = fh_names.get(b.farmhouse_id)
        b.bookie_name = user_names.get(b.bookie_id)
    return bookings

# ---------------------------------------------------------------------------
# Constants
# Slice #29 sources hold duration from the DB-backed SystemSettings singleton.
# DEFAULT_HOLD_HOURS is kept as a fallback constant in case the DB row is
# unreachable, but the primary source is get_or_create_settings(db).hold_duration_hours.
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
    if fh is None or fh.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Farmhouse not found")
    if fh.status != "active":
        raise HTTPException(status_code=400, detail="Farmhouse is not active")

    # ── Business rule validation (slice #29) ────────────────────────────────
    # Checks: min advance notice, blackout dates, operating hours.
    # The "start_at in the future" guard above is intentionally NOT repeated
    # here to avoid a double-check conflict (see booking_rules.py module docs).
    validate_booking_window(db, farmhouse=fh, start_at=start_at, end_at=end_at, now=now)

    # ── Create hold ─────────────────────────────────────────────────────────
    # Source hold duration from the DB-backed SystemSettings singleton (slice #29).
    # Falls back to DEFAULT_HOLD_HOURS if get_or_create_settings raises unexpectedly.
    db_settings = get_or_create_settings(db)
    hold_hours = db_settings.hold_duration_hours

    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=current_user.id,
        tenant_id=current_user.tenant_id,
        status="hold",
        start_at=start_at,
        end_at=end_at,
        buffer_minutes_snapshot=fh.buffer_minutes,
        expires_at=now + timedelta(hours=hold_hours),
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
    # NOTIFY: admins of a new hold (wired in #27)
    dispatch_booking_event(
        db,
        type="hold.created",
        booking=booking,
        actor_id=current_user.id,
        critical=True,
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
    # Guard: an expired hold cannot be submitted — the bookie must place a new hold.
    _now = datetime.now(timezone.utc)
    if is_hold_expired(booking, _now):
        raise HTTPException(
            status_code=409,
            detail="Hold has expired; please place a new hold",
        )
    if booking.bookie_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to submit this booking")

    # ── Re-validate business rules (slice #29) ──────────────────────────────
    # Rules may have changed since the hold was placed (e.g. a new blackout was
    # added or operating hours were updated).  Re-run the same checks so the
    # booking cannot slip through a window that has since closed.
    _fh: Farmhouse | None = db.get(Farmhouse, booking.farmhouse_id)
    if _fh is not None:
        validate_booking_window(
            db,
            farmhouse=_fh,
            start_at=booking.start_at,
            end_at=booking.end_at,
            now=_now,
        )

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
    # NOTIFY: admins of a submitted request (wired in #27)
    dispatch_booking_event(
        db,
        type="request.submitted",
        booking=booking,
        actor_id=current_user.id,
        critical=True,
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

    # Scope to the requester's estate.
    from app.tenancy import tenant_clause
    query = query.filter(tenant_clause(Booking.tenant_id, current_user.tenant_id))

    if current_user.role != "admin":
        query = query.filter(Booking.bookie_id == current_user.id)

    # Lazy expiry: exclude holds that have timed-out but haven't been swept yet.
    # This keeps the listing consistent with the availability endpoint without
    # depending on the APScheduler job having run.
    _now = datetime.now(timezone.utc)
    query = query.filter(
        not_(and_(
            Booking.status == "hold",
            Booking.expires_at.isnot(None),
            Booking.expires_at < _now,
        ))
    )

    if status is not None:
        query = query.filter(Booking.status == status)
    if farmhouse_id is not None:
        query = query.filter(Booking.farmhouse_id == farmhouse_id)

    return _enrich(db, query.order_by(Booking.created_at.desc()).all())


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
    return _enrich(db, [booking])[0]


# ---------------------------------------------------------------------------
# POST /api/bookings/{booking_id}/approve  (slice #23)
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/approve", response_model=BookingRead)
def approve_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> Booking:
    """Approve a pending booking — transition it to 'booked'.

    Preconditions:
      - booking exists                              (404)
      - booking.status == 'pending'                 (409)
      - no status='booked' booking on the same farmhouse has a buffered range
        overlapping this booking's buffered range   (409 with conflict_booking_id)

    On success:
      - status  -> 'booked'
      - decided_by = admin.id
      - decided_at = now (UTC)
      - 'booking.approved' activity log entry added in the SAME transaction

    The overlap check and the status write are performed in ONE transaction.
    SQLite serialises writers, so two concurrent approve calls are serialised
    by the DB engine itself — the second one will see the first booking as
    'booked' and correctly get a 409.
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Booking is not in 'pending' status (current: {booking.status})",
        )

    # The conflict check and the booked-write must be atomic. Hold a
    # process-level lock so concurrent approvals cannot both pass the overlap
    # SELECT before one commits (SQLite alone does not prevent this write-skew).
    with _approve_lock:
        # Re-read inside the lock in case another approval just committed.
        db.refresh(booking)
        if booking.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Booking is not in 'pending' status (current: {booking.status})",
            )

        # ── Overlap check (within the same transaction) ─────────────────────
        conflict = find_booked_conflict(
            db,
            farmhouse_id=booking.farmhouse_id,
            start_at=booking.start_at,
            end_at=booking.end_at,
            buffer_minutes=booking.buffer_minutes_snapshot,
            exclude_booking_id=booking_id,
        )
        if conflict is not None:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Time slot conflicts with an existing confirmed booking",
                    "conflict_booking_id": conflict.id,
                },
            )

        # ── Approve: set status + metadata ─────────────────────────────────
        now = datetime.now(timezone.utc)
        booking.status     = "booked"
        booking.decided_by = admin.id
        booking.decided_at = now

        log_activity(
            db,
            actor_id=admin.id,
            action="booking.approved",
            target_type="booking",
            target_id=booking_id,
        )
        # NOTIFY: bookie + admins of approval (wired in #27)
        dispatch_booking_event(
            db,
            type="booking.approved",
            booking=booking,
            actor_id=admin.id,
            critical=True,
        )
        db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# POST /api/bookings/direct  (admin direct booking — Issues.md gap)
# ---------------------------------------------------------------------------

@router.post("/bookings/direct", response_model=BookingRead, status_code=201)
def direct_book(
    body: DirectBookRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> Booking:
    """Admin creates a confirmed booking in one step (status -> 'booked').

    Skips the hold/submit/approve flow. Runs the same future/window validation
    and the exclusive-overlap conflict check as /approve, under the same
    process-level lock, so confirmed double bookings remain impossible.

    Returns 409 {detail, conflict_booking_id} if the slot conflicts with an
    existing confirmed booking.
    """
    now = datetime.now(timezone.utc)

    start_at = body.start_at
    end_at = body.end_at
    if start_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_at must include timezone info")
    if end_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="end_at must include timezone info")
    start_at = start_at.astimezone(timezone.utc)
    end_at = end_at.astimezone(timezone.utc)

    if start_at >= end_at:
        raise HTTPException(status_code=422, detail="start_at must be strictly before end_at")
    if start_at <= now:
        raise HTTPException(status_code=422, detail="start_at must be in the future")

    fh: Farmhouse | None = db.get(Farmhouse, body.farmhouse_id)
    if fh is None or fh.tenant_id != admin.tenant_id:
        raise HTTPException(status_code=404, detail="Farmhouse not found")
    if fh.status != "active":
        raise HTTPException(status_code=400, detail="Farmhouse is not active")

    validate_booking_window(db, farmhouse=fh, start_at=start_at, end_at=end_at, now=now)

    with _approve_lock:
        conflict = find_booked_conflict(
            db,
            farmhouse_id=fh.id,
            start_at=start_at,
            end_at=end_at,
            buffer_minutes=fh.buffer_minutes,
        )
        if conflict is not None:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Time slot conflicts with an existing confirmed booking",
                    "conflict_booking_id": conflict.id,
                },
            )

        booking = Booking(
            farmhouse_id=fh.id,
            bookie_id=admin.id,
            tenant_id=admin.tenant_id,
            status="booked",
            start_at=start_at,
            end_at=end_at,
            buffer_minutes_snapshot=fh.buffer_minutes,
            client_name=body.client_name,
            client_contact=body.client_contact,
            event_type=body.event_type,
            event_info=body.event_info,
            notes=body.notes,
            quoted_price=body.quoted_price,
            decided_by=admin.id,
            decided_at=now,
        )
        db.add(booking)
        db.flush()

        log_activity(
            db,
            actor_id=admin.id,
            action="booking.approved",
            target_type="booking",
            target_id=booking.id,
            note="direct booking by admin",
        )
        dispatch_booking_event(
            db,
            type="booking.approved",
            booking=booking,
            actor_id=admin.id,
            critical=True,
        )
        db.commit()
    db.refresh(booking)
    return _enrich(db, [booking])[0]


# ---------------------------------------------------------------------------
# GET /api/bookings/{booking_id}/conflicts  (slice #24)
# ---------------------------------------------------------------------------

@router.get("/bookings/{booking_id}/conflicts", response_model=List[BookingRead])
def get_booking_conflicts(
    booking_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> list:
    """Return overlapping hold/pending bookings for a given (usually booked) booking.

    Called by the UI immediately after a successful /approve to discover the
    "losers" — other hold/pending requests on the same farmhouse whose
    buffered range overlaps the just-approved booking. The admin can then
    reject them via /reject or /reject-batch.

    Preconditions:
      - booking exists       (404)
      - admin only           (403)

    Returns an empty list if there are no overlapping hold/pending bookings.
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    return find_overlapping_unresolved(
        db,
        farmhouse_id=booking.farmhouse_id,
        start_at=booking.start_at,
        end_at=booking.end_at,
        buffer_minutes=booking.buffer_minutes_snapshot,
        exclude_booking_id=booking_id,
    )


# ---------------------------------------------------------------------------
# POST /api/bookings/reject-batch  (slice #24) — MUST be before /{booking_id}/reject
# ---------------------------------------------------------------------------

@router.post("/bookings/reject-batch", response_model=RejectBatchResponse)
def reject_batch(
    body: RejectBatchRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> RejectBatchResponse:
    """Batch-reject hold/pending bookings (admin only).

    For each id in booking_ids:
      - If the booking is hold or pending -> reject it (status='rejected',
        decided_by/decided_at/reason set) + emit 'request.rejected' activity log.
      - Otherwise (booked, already-rejected, canceled, expired, missing) ->
        add to skipped list with a reason_skipped string.

    All changes are committed in a single transaction at the end.

    Response:
      { rejected: [ids], skipped: [{id, reason_skipped}] }
    """
    now = datetime.now(timezone.utc)
    rejected_ids: list[int] = []
    skipped: list[dict] = []

    for bid in body.booking_ids:
        booking: Booking | None = db.get(Booking, bid)
        if booking is None:
            skipped.append({"id": bid, "reason_skipped": "booking not found"})
            continue
        if booking.status not in ("hold", "pending"):
            skipped.append({
                "id": bid,
                "reason_skipped": f"booking is not rejectable (status: {booking.status})",
            })
            continue

        booking.status     = "rejected"
        booking.decided_by = admin.id
        booking.decided_at = now
        booking.reason     = body.reason

        # NOTIFY: affected bookie on rejection (wired in #27)
        dispatch_booking_event(
            db,
            type="request.rejected",
            booking=booking,
            actor_id=admin.id,
            critical=True,
        )
        log_activity(
            db,
            actor_id=admin.id,
            action="request.rejected",
            target_type="booking",
            target_id=bid,
            note=body.reason,
        )
        rejected_ids.append(bid)

    db.commit()
    return RejectBatchResponse(
        rejected=rejected_ids,
        skipped=[{"id": s["id"], "reason_skipped": s["reason_skipped"]} for s in skipped],
    )


# ---------------------------------------------------------------------------
# POST /api/bookings/{booking_id}/reject  (slice #24)
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/reject", response_model=BookingRead)
def reject_booking(
    booking_id: int,
    body: RejectRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> Booking:
    """Reject a hold or pending booking (admin only).

    Preconditions:
      - booking exists                        (404)
      - booking.status in ('hold', 'pending') (409 if not rejectable)
      - body.reason is non-empty              (422)

    On success:
      - status     -> 'rejected'
      - decided_by  = admin.id
      - decided_at  = now (UTC)
      - reason      = body.reason
      - 'request.rejected' activity log entry added in the SAME transaction.

    The booked row for the winning booking is NEVER touched here.
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status not in ("hold", "pending"):
        raise HTTPException(
            status_code=409,
            detail=f"Booking is not in a rejectable state (current: {booking.status})",
        )

    now = datetime.now(timezone.utc)
    booking.status     = "rejected"
    booking.decided_by = admin.id
    booking.decided_at = now
    booking.reason     = body.reason

    # NOTIFY: affected bookie on rejection (wired in #27)
    dispatch_booking_event(
        db,
        type="request.rejected",
        booking=booking,
        actor_id=admin.id,
        critical=True,
    )
    log_activity(
        db,
        actor_id=admin.id,
        action="request.rejected",
        target_type="booking",
        target_id=booking_id,
        note=body.reason,
    )
    db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# POST /api/bookings/{booking_id}/cancel  (slice #26 — admin only)
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/cancel", response_model=BookingRead)
def cancel_booking(
    booking_id: int,
    body: CancelRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> Booking:
    """Admin cancels a pending or booked booking.

    Preconditions:
      - booking exists                           (404)
      - booking.status in ('pending', 'booked')  (409 otherwise)
      - body.reason is non-empty                 (422)

    On success:
      - status      -> 'canceled'
      - decided_by   = admin.id
      - decided_at   = now (UTC)
      - cancel_reason = body.reason
      - 'booking.canceled' activity log entry added in the SAME transaction.

    A canceled booking no longer occupies the slot (find_booked_conflict
    filters on status='booked' only), so approving an overlapping pending
    now succeeds automatically.
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status not in ("pending", "booked"):
        raise HTTPException(
            status_code=409,
            detail=f"Only pending or booked bookings can be canceled via this endpoint (current: {booking.status})",
        )

    now = datetime.now(timezone.utc)
    booking.status      = "canceled"
    booking.decided_by  = admin.id
    booking.decided_at  = now
    booking.cancel_reason = body.reason

    # NOTIFY: admin canceled booking (wired in #27)
    dispatch_booking_event(
        db,
        type="booking.canceled",
        booking=booking,
        actor_id=admin.id,
        critical=True,
    )
    log_activity(
        db,
        actor_id=admin.id,
        action="booking.canceled",
        target_type="booking",
        target_id=booking_id,
        note=body.reason,
    )
    db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# POST /api/bookings/{booking_id}/withdraw  (slice #26 — owner OR admin)
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/withdraw", response_model=BookingRead)
def withdraw_booking(
    booking_id: int,
    body: WithdrawRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Booking:
    """Bookie (or admin) withdraws their own hold or pending booking.

    Preconditions:
      - booking exists                              (404)
      - requester is owner OR admin                 (403)
      - booking.status in ('hold', 'pending')       (409; use /request-cancel for booked)

    On success:
      - status              -> 'canceled'
      - cancel_requested_by  = current_user.id  (traceability)
      - cancel_reason        = body.reason if provided, else 'withdrawn by bookie'
      - decided_by stays null (self-withdraw)
      - 'booking.withdrawn' activity log entry.
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Permission: owner or admin
    if booking.bookie_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to withdraw this booking")

    if booking.status not in ("hold", "pending"):
        raise HTTPException(
            status_code=409,
            detail=f"Only hold or pending bookings can be withdrawn (current: {booking.status}). Use /request-cancel for booked bookings.",
        )

    booking.status              = "canceled"
    booking.cancel_requested_by = current_user.id
    booking.cancel_reason       = body.reason if (body.reason and body.reason.strip()) else "withdrawn by bookie"

    # NOTIFY: bookie withdrew booking (wired in #27) — non-critical (in-app only)
    dispatch_booking_event(
        db,
        type="booking.withdrawn",
        booking=booking,
        actor_id=current_user.id,
        critical=False,
    )
    log_activity(
        db,
        actor_id=current_user.id,
        action="booking.withdrawn",
        target_type="booking",
        target_id=booking_id,
        note=booking.cancel_reason,
    )
    db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# POST /api/bookings/{booking_id}/request-cancel  (slice #26 — owner OR admin)
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/request-cancel", response_model=BookingRead)
def request_cancel(
    booking_id: int,
    body: RequestCancelBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Booking:
    """Bookie requests cancellation of their own BOOKED event.

    Does NOT change status (stays 'booked'; keeps occupying the slot until admin
    confirms). Sets cancel_requested_at, cancel_requested_by, cancel_reason.

    Preconditions:
      - booking exists                              (404)
      - requester is owner OR admin                 (403)
      - booking.status == 'booked'                  (409)
      - cancel_requested_at is None (not already requested)   (409)
      - body.reason is non-empty                    (422)

    On success:
      - cancel_requested_at  = now (UTC)
      - cancel_requested_by  = current_user.id
      - cancel_reason        = body.reason
      - status stays 'booked'
      - 'booking.cancel_requested' activity log entry.
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Permission: owner or admin
    if booking.bookie_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to request cancellation of this booking")

    if booking.status != "booked":
        raise HTTPException(
            status_code=409,
            detail=f"Only booked bookings can have a cancellation requested (current: {booking.status})",
        )
    if booking.cancel_requested_at is not None:
        raise HTTPException(
            status_code=409,
            detail="A cancellation has already been requested for this booking",
        )

    now = datetime.now(timezone.utc)
    booking.cancel_requested_at  = now
    booking.cancel_requested_by  = current_user.id
    booking.cancel_reason        = body.reason

    # NOTIFY: bookie requested cancellation (wired in #27)
    dispatch_booking_event(
        db,
        type="booking.cancel_requested",
        booking=booking,
        actor_id=current_user.id,
        critical=True,
    )
    log_activity(
        db,
        actor_id=current_user.id,
        action="booking.cancel_requested",
        target_type="booking",
        target_id=booking_id,
        note=body.reason,
    )
    db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# POST /api/bookings/{booking_id}/confirm-cancel  (slice #26 — admin only)
# ---------------------------------------------------------------------------

@router.post("/bookings/{booking_id}/confirm-cancel", response_model=BookingRead)
def confirm_cancel(
    booking_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
) -> Booking:
    """Admin finalizes a booked event that has a pending cancellation request.

    Preconditions:
      - booking exists                              (404)
      - booking.status == 'booked'                  (409)
      - cancel_requested_at is not None             (409)

    On success:
      - status     -> 'canceled'
      - decided_by  = admin.id
      - decided_at  = now (UTC)
      - 'booking.cancel_confirmed' activity log entry.

    Note: Admins may alternatively use /cancel directly to cancel a booked
    booking without requiring a prior cancellation request.
    """
    booking: Booking | None = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != "booked":
        raise HTTPException(
            status_code=409,
            detail=f"Only booked bookings can be confirm-canceled (current: {booking.status})",
        )
    if booking.cancel_requested_at is None:
        raise HTTPException(
            status_code=409,
            detail="No cancellation has been requested for this booking",
        )

    now = datetime.now(timezone.utc)
    booking.status      = "canceled"
    booking.decided_by  = admin.id
    booking.decided_at  = now

    # NOTIFY: admin confirmed cancellation (wired in #27)
    dispatch_booking_event(
        db,
        type="booking.cancel_confirmed",
        booking=booking,
        actor_id=admin.id,
        critical=True,
    )
    log_activity(
        db,
        actor_id=admin.id,
        action="booking.cancel_confirmed",
        target_type="booking",
        target_id=booking_id,
    )
    db.commit()
    db.refresh(booking)
    return booking
