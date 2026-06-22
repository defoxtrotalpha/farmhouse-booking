"""SQLAlchemy models package.

Import all model modules here so that ``Base.metadata`` is fully populated for
Alembic autogenerate and ``create_all`` in tests. Later slices append their
models and re-export them from this package.
"""
from __future__ import annotations

from app.db import Base
from app.models.user import User  # noqa: F401
from app.models.invite import InviteToken  # noqa: F401
from app.models.farmhouse import Farmhouse  # noqa: F401
from app.models.activity import ActivityLog  # noqa: F401
from app.models.policy import Policy  # noqa: F401
from app.models.booking import Booking  # noqa: F401
from app.models.settings import SystemSettings  # noqa: F401
from app.models.blackout import BlackoutDate  # noqa: F401

__all__ = ["Base", "User", "Farmhouse", "ActivityLog", "Policy", "Booking",
           "SystemSettings", "BlackoutDate"]
