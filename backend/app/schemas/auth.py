"""Pydantic schemas for authentication."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    # Company name (or slug). Optional so existing single-tenant clients/tests work.
    tenant: Optional[str] = None
    # Sign-in identifier — supply either email, username, or the generic identifier.
    email: Optional[str] = None
    username: Optional[str] = None
    identifier: Optional[str] = None
    password: str


class SignupRequest(BaseModel):
    """POST /api/auth/signup — request a new company (pending approval)."""

    company_name: str
    name: str
    email: str
    password: str


class SignupResponse(BaseModel):
    """Returned after a company signup request — no tokens (awaiting approval)."""

    status: str = "pending"
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


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
    email: Optional[str] = None
    username: Optional[str] = None
    name: str
    role: str
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None
    tenant_slug: Optional[str] = None
