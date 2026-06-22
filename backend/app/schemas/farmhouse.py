"""Pydantic schemas for Farmhouse endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FarmhouseCreate(BaseModel):
    name: str
    description: str = ""
    capacity: int | None = None
    buffer_minutes: int = Field(default=0, ge=0)
    operating_hours: Any | None = None  # stored as text; pass dict or None


class FarmhouseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    capacity: int | None = None
    buffer_minutes: int | None = Field(default=None, ge=0)
    operating_hours: Any | None = None
    status: str | None = None  # 'active' | 'disabled'


class FarmhouseRead(BaseModel):
    id: int
    name: str
    description: str
    capacity: int | None
    buffer_minutes: int
    operating_hours: Any | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
