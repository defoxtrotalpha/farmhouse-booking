"""Settings router — slice #29.

GET  /api/settings        any active user  -> 200 SettingsRead
PATCH /api/settings       admin only       -> 200 SettingsRead
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.models.settings import get_or_create_settings
from app.schemas.settings import SettingsPatch, SettingsRead
from app.services.activity import log_activity

router = APIRouter(prefix="/api", tags=["settings"])

_HHMMRE = re.compile(r"^\d{2}:\d{2}$")


def _validate_hhMM(value: str, field: str) -> None:
    """Raise 422 if value is not a valid HH:MM time string."""
    if not _HHMMRE.match(value):
        raise HTTPException(
            status_code=422,
            detail=f"{field} must be in HH:MM format (e.g. '09:00')",
        )
    h, m = int(value[:2]), int(value[3:])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise HTTPException(
            status_code=422,
            detail=f"{field} time values out of range",
        )


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=SettingsRead)
def get_settings_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return current system settings. Any authenticated user may read."""
    return get_or_create_settings(db)


# ---------------------------------------------------------------------------
# PATCH /api/settings
# ---------------------------------------------------------------------------

@router.patch("/settings", response_model=SettingsRead)
def patch_settings(
    body: SettingsPatch,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Partially update system settings. Admin only."""
    # Validate HH:MM format for any supplied operating hours field.
    if body.operating_hours_start is not None:
        _validate_hhMM(body.operating_hours_start, "operating_hours_start")
    if body.operating_hours_end is not None:
        _validate_hhMM(body.operating_hours_end, "operating_hours_end")

    s = get_or_create_settings(db)

    # Determine the effective start/end after applying the patch.
    new_start = body.operating_hours_start if body.operating_hours_start is not None else s.operating_hours_start
    new_end   = body.operating_hours_end   if body.operating_hours_end   is not None else s.operating_hours_end

    # Validate start < end when both values are present.
    if new_start and new_end:
        h_s, m_s = int(new_start[:2]), int(new_start[3:])
        h_e, m_e = int(new_end[:2]),   int(new_end[3:])
        if (h_s, m_s) >= (h_e, m_e):
            raise HTTPException(
                status_code=422,
                detail="operating_hours_start must be strictly before operating_hours_end",
            )

    # Apply the partial update.
    if body.hold_duration_hours          is not None: s.hold_duration_hours          = body.hold_duration_hours
    if body.min_advance_notice_minutes   is not None: s.min_advance_notice_minutes   = body.min_advance_notice_minutes
    if body.default_buffer_minutes       is not None: s.default_buffer_minutes       = body.default_buffer_minutes
    if body.operating_hours_start        is not None: s.operating_hours_start        = body.operating_hours_start
    if body.operating_hours_end          is not None: s.operating_hours_end          = body.operating_hours_end

    s.updated_at = datetime.now(timezone.utc)

    log_activity(
        db,
        actor_id=current_user.id,
        action="settings.updated",
        target_type="settings",
        target_id=s.id,
    )
    db.commit()
    db.refresh(s)
    return s
