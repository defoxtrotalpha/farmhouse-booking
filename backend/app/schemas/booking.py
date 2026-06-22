"""Booking-related Pydantic schemas.

Only AvailabilityEntry is needed for slice #21.
Later slices (hold, approve, etc.) will add BookingCreate, BookingRead, etc.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AvailabilityEntry(BaseModel):
    """Shape returned by GET /api/farmhouses/{id}/availability."""

    id: int
    status: str
    start_at: datetime
    end_at: datetime
    bookie_id: int

    model_config = {"from_attributes": True}
