"""Pydantic schemas for the notifications endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: int
    recipient_id: int
    type: str
    title: str
    body: str | None
    booking_id: int | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
