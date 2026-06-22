"""Pydantic schemas for the invite-a-bookie slice."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator


class InviteRequest(BaseModel):
    name: str
    email: EmailStr


class InviteResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str

    model_config = {"from_attributes": True}


class SetPasswordRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
