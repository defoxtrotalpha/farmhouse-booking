"""Pydantic schemas for SystemSettings (slice #29)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SettingsRead(BaseModel):
    id: int
    hold_duration_hours: int
    min_advance_notice_minutes: int
    default_buffer_minutes: int
    operating_hours_start: Optional[str] = None
    operating_hours_end:   Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingsPatch(BaseModel):
    hold_duration_hours:          Optional[int] = None
    min_advance_notice_minutes:   Optional[int] = None
    default_buffer_minutes:       Optional[int] = None
    operating_hours_start:        Optional[str] = None
    operating_hours_end:          Optional[str] = None
