"""Tenant SQLAlchemy model — top-level isolation boundary ("estate").

Each estate has its own admins, bookies, farmhouses, bookings, policies,
blackout dates and activity log. Rows in scoped tables carry a nullable
``tenant_id`` so that the existing single-tenant test fixtures (which build
rows directly without a tenant) keep working: ``tenant_id IS NULL`` behaves as
one implicit shared tenant, while real estates isolate by id.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TZDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Approval lifecycle: 'pending' (awaiting global-admin review) ->
    # 'approved' (active, members may sign in) | 'rejected' (denied).
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="approved", index=True
    )
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, default=_utcnow)
