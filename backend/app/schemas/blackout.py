"""Pydantic schemas for BlackoutDate (slice #29)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class BlackoutCreate(BaseModel):
    farmhouse_id: Optional[int] = None
    start_date: date
    end_date:   date
    reason:     Optional[str] = None


class BlackoutRead(BaseModel):
    id: int
    farmhouse_id: Optional[int] = None
    start_date: date
    end_date:   date
    reason:     Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
