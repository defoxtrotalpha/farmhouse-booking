"""Pydantic schemas for platform (global-admin) operations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CompanyCreateRequest(BaseModel):
    """POST /api/companies — create an approved company + its first admin."""

    company_name: str
    admin_name: str
    admin_email: str
    admin_password: str


class CompanyRead(BaseModel):
    id: int
    name: str
    slug: str
    status: str
    created_at: datetime
    admin_name: Optional[str] = None
    admin_email: Optional[str] = None
    admin_count: int = 0
    member_count: int = 0
    farmhouse_count: int = 0


class GlobalAdminCreateRequest(BaseModel):
    name: str
    email: str
    password: str


class GlobalAdminRead(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    created_at: datetime
