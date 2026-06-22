"""Pydantic schemas for authentication."""
from __future__ import annotations

from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: str) -> str:
        import email_validator
        result = email_validator.validate_email(v, check_deliverability=False)
        return result.normalized


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
