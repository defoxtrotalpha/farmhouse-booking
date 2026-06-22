"""Booking business-rule validator — slice #29.

validate_booking_window(db, *, farmhouse, start_at, end_at, now=None) -> None

Called from:
  - POST /api/bookings/hold   (after farmhouse-active / future / start<end checks)
  - POST /api/bookings/{id}/submit  (re-validate in case rules changed)

Raises fastapi.HTTPException(status_code=422, detail=<message>) on violation.

Rules enforced
--------------
1. MIN ADVANCE NOTICE
   If settings.min_advance_notice_minutes > 0, require
   start_at >= now + that many minutes.  When 0 (default), the rule is OFF.

2. BLACKOUT DATES
   The booking's date span in Asia/Karachi (from start_at date through end_at
   date inclusive) must not intersect any blackout whose farmhouse_id is NULL
   (global) OR matches this farmhouse's id.

3. OPERATING HOURS (single-day bookings only)
   Determine the effective operating window:
     - Per-farmhouse farmhouse.operating_hours (JSON {"start":"HH:MM","end":"HH:MM"})
       takes precedence over global settings.operating_hours_start/end.
     - If an operating window is in effect AND the booking starts and ends on the
       SAME Asia/Karachi calendar date, enforce:
         booking local start time-of-day >= open
         booking local end   time-of-day <= close
     - NOTE: for multi-day bookings (start and end on different Asia/Karachi
       calendar dates) operating-hours enforcement is SKIPPED because a simple
       time-of-day check becomes ambiguous (which day's window applies?).
       TODO: per-day enforcement in a future version.
   If no operating window is configured anywhere, the rule is skipped.

Note: The "start_at must be in the future" check is enforced directly in the
hold-create handler (before calling this function) and is NOT repeated here, to
avoid a double-check conflict.  At submit time only the rules above are
re-validated.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.blackout import BlackoutDate
from app.models.farmhouse import Farmhouse
from app.models.settings import get_or_create_settings

_TZ = ZoneInfo("Asia/Karachi")
_HHMMRE = re.compile(r"^\d{2}:\d{2}$")


def _parse_time(hhmm: str) -> time:
    h, m = int(hhmm[:2]), int(hhmm[3:])
    return time(h, m)


def validate_booking_window(
    db: Session,
    *,
    farmhouse: Farmhouse,
    start_at: datetime,   # UTC-aware
    end_at: datetime,     # UTC-aware
    now: datetime | None = None,
) -> None:
    """Validate a booking slot against all configured business rules.

    Raises HTTPException(422) when any rule is violated.
    All datetime arguments must be UTC-aware.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    settings = get_or_create_settings(db)

    # ------------------------------------------------------------------
    # Rule 1: Min advance notice
    # ------------------------------------------------------------------
    if settings.min_advance_notice_minutes > 0:
        earliest_allowed = now + timedelta(minutes=settings.min_advance_notice_minutes)
        if start_at < earliest_allowed:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Booking must be at least {settings.min_advance_notice_minutes} "
                    f"minutes in advance"
                ),
            )

    # ------------------------------------------------------------------
    # Rule 2: Blackout dates
    # Convert booking UTC times to Asia/Karachi calendar dates.
    # ------------------------------------------------------------------
    local_start = start_at.astimezone(_TZ)
    local_end   = end_at.astimezone(_TZ)
    booking_start_date = local_start.date()
    booking_end_date   = local_end.date()

    # Date range overlap: blackout.start_date <= booking_end_date
    #                 AND blackout.end_date   >= booking_start_date
    blackout = (
        db.query(BlackoutDate)
        .filter(
            or_(
                BlackoutDate.farmhouse_id.is_(None),
                BlackoutDate.farmhouse_id == farmhouse.id,
            ),
            BlackoutDate.start_date <= booking_end_date,
            BlackoutDate.end_date   >= booking_start_date,
        )
        .first()
    )
    if blackout is not None:
        label = blackout.reason or str(blackout.start_date)
        raise HTTPException(
            status_code=422,
            detail=f"Selected dates include a blackout/holiday: {label}",
        )

    # ------------------------------------------------------------------
    # Rule 3: Operating hours (single-day bookings only)
    # ------------------------------------------------------------------
    # Determine effective window: per-farmhouse takes precedence.
    op_start: str | None = None
    op_end:   str | None = None

    if farmhouse.operating_hours:
        try:
            oh = json.loads(farmhouse.operating_hours)
            if isinstance(oh, dict) and "start" in oh and "end" in oh:
                op_start = oh["start"]
                op_end   = oh["end"]
        except (json.JSONDecodeError, TypeError):
            pass  # fall through to global settings

    if op_start is None:
        if settings.operating_hours_start and settings.operating_hours_end:
            op_start = settings.operating_hours_start
            op_end   = settings.operating_hours_end

    if op_start and op_end:
        if booking_start_date == booking_end_date:
            # Single-day booking: apply time-of-day check.
            open_t  = _parse_time(op_start)
            close_t = _parse_time(op_end)
            # Strip sub-minute precision for a clean comparison.
            bk_start_t = local_start.time().replace(second=0, microsecond=0)
            bk_end_t   = local_end.time().replace(second=0, microsecond=0)

            if bk_start_t < open_t or bk_end_t > close_t:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Booking must be within operating hours "
                        f"({op_start}–{op_end} Asia/Karachi)"
                    ),
                )
        # else: multi-day booking — operating-hours enforcement is SKIPPED.
        # See module docstring for rationale.
