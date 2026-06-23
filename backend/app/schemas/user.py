"""User-related Pydantic schemas (admin user/bookie management)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserRead(BaseModel):
    """Shape returned by GET /api/users (admin only).

    `accepted` is True once the invited user has set a password (activated
    their account). It lets admins see, at a glance, which invited bookies
    have onboarded and which are still pending.
    """

    id: int
    name: str
    email: Optional[str] = None
    username: Optional[str] = None
    role: str
    is_active: bool
    accepted: bool
    is_primary: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """PATCH /api/users/{id} request body (admin only)."""

    is_active: Optional[bool] = None


class DirectUserCreate(BaseModel):
    """POST /api/users/direct — admin creates an active user with credentials."""

    name: str
    username: str
    password: str
    role: str = "bookie"
    email: Optional[str] = None
