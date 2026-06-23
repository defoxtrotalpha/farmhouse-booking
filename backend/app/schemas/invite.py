"""Pydantic schemas for the invite-a-bookie slice."""
from __future__ import annotations

from pydantic import BaseModel, field_validator


class InviteRequest(BaseModel):
    name: str
    email: str
    role: str = "bookie"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        return v if v in ("bookie", "admin") else "bookie"

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: str) -> str:
        import email_validator
        result = email_validator.validate_email(v, check_deliverability=False)
        return result.normalized


class InviteResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    set_password_url: str | None = None

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
