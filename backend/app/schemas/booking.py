"""Booking-related Pydantic schemas.

Slice #21: AvailabilityEntry
Slice #22: HoldRequest, SubmitRequest, BookingRead
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AvailabilityEntry(BaseModel):
    """Shape returned by GET /api/farmhouses/{id}/availability."""

    id: int
    status: str
    start_at: datetime
    end_at: datetime
    bookie_id: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Slice #22 — Hold / Submit
# ---------------------------------------------------------------------------

class HoldRequest(BaseModel):
    """POST /api/bookings/hold request body."""

    farmhouse_id: int
    start_at: datetime
    end_at: datetime


class SubmitRequest(BaseModel):
    """POST /api/bookings/{id}/submit request body."""

    client_name: str
    client_contact: str
    event_type: Optional[str] = None
    event_info: Optional[str] = None
    notes: Optional[str] = None
    quoted_price: Optional[float] = None


class BookingRead(BaseModel):
    """Full booking response shape (used by hold/submit/list/get endpoints)."""

    id: int
    farmhouse_id: int
    bookie_id: int
    status: str
    start_at: datetime
    end_at: datetime
    buffer_minutes_snapshot: int
    client_name: Optional[str] = None
    client_contact: Optional[str] = None
    event_type: Optional[str] = None
    event_info: Optional[str] = None
    notes: Optional[str] = None
    quoted_price: Optional[float] = None
    expires_at: Optional[datetime] = None
    decided_by: Optional[int] = None
    decided_at: Optional[datetime] = None
    reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
