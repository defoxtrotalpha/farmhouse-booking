"""ActivityLog SQLAlchemy model — append-only audit table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text

from app.db import Base, TZDateTime


class ActivityLog(Base):
    """Append-only audit log entry.

    actor_id is nullable to support future system-generated entries
    (e.g. hold expiry daemon) where no human actor exists.
    """

    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )
    actor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), nullable=True)
    target_id = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(
        TZDateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_activity_logs_actor_id", "actor_id"),
        Index("ix_activity_logs_created_at", "created_at"),
    )
