"""Pydantic schemas for the Activity Log slice."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ActivityLogRead(BaseModel):
    """Response schema for a single activity log entry."""

    id: int
    actor_id: Optional[int]
    action: str
    target_type: Optional[str]
    target_id: Optional[int]
    note: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
