"""Pydantic schemas for Policy endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PolicyCreate(BaseModel):
    title: str
    body: str


class PolicyUpdate(BaseModel):
    title: str | None = None
    body: str | None = None


class PolicyRead(BaseModel):
    id: int
    title: str
    body: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
