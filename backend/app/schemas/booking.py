"""Booking-related Pydantic schemas.

Slice #21: AvailabilityEntry
Slice #22: HoldRequest, SubmitRequest, BookingRead
Slice #24: RejectRequest, RejectBatchRequest, RejectBatchResponse, SkippedEntry
Slice #26: CancelRequest, WithdrawRequest, RequestCancelRequest
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator


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
    # Cancellation request fields (slice #26)
    cancel_requested_at: Optional[datetime] = None
    cancel_requested_by: Optional[int] = None
    cancel_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Enriched display fields (attached by the router; not stored on the model).
    # Let the UI show "who booked it" and the venue name without extra lookups.
    farmhouse_name: Optional[str] = None
    bookie_name: Optional[str] = None

    model_config = {"from_attributes": True}


class DirectBookRequest(BaseModel):
    """POST /api/bookings/direct request body (admin only).

    Lets an admin create a confirmed booking in one step (no hold/submit/approve
    flow). Resolves the Issues.md gap: "for admin, it should not ask me to place
    hold, it should give me option to book directly".
    """

    farmhouse_id: int
    start_at: datetime
    end_at: datetime
    client_name: str
    client_contact: str
    event_type: Optional[str] = None
    event_info: Optional[str] = None
    notes: Optional[str] = None
    quoted_price: Optional[float] = None


# ---------------------------------------------------------------------------
# Slice #24 — Reject / Reject-batch
# ---------------------------------------------------------------------------

class RejectRequest(BaseModel):
    """POST /api/bookings/{id}/reject request body."""

    reason: str

    @field_validator("reason")
    @classmethod
    def reason_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason must not be empty")
        return v


class RejectBatchRequest(BaseModel):
    """POST /api/bookings/reject-batch request body."""

    booking_ids: List[int]
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason must not be empty")
        return v


class SkippedEntry(BaseModel):
    """One entry in the 'skipped' list of a reject-batch response."""

    id: int
    reason_skipped: str


class RejectBatchResponse(BaseModel):
    """POST /api/bookings/reject-batch response body."""

    rejected: List[int]
    skipped: List[SkippedEntry]


# ---------------------------------------------------------------------------
# Slice #26 — Cancellation / Withdraw / Request-cancel / Confirm-cancel
# ---------------------------------------------------------------------------

class CancelRequest(BaseModel):
    """POST /api/bookings/{id}/cancel request body (admin only).

    Reason is optional — an admin may cancel without giving one.
    """

    reason: Optional[str] = None


class WithdrawRequest(BaseModel):
    """POST /api/bookings/{id}/withdraw request body (owner or admin)."""

    reason: Optional[str] = None


class RequestCancelBody(BaseModel):
    """POST /api/bookings/{id}/request-cancel request body (owner or admin)."""

    reason: str

    @field_validator("reason")
    @classmethod
    def reason_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason must not be empty")
        return v
