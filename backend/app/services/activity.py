"""Activity logging service — single chokepoint for all audit entries.

Commit semantics
----------------
``log_activity`` adds the new row and flushes (so the row gets an ``id``
immediately), but does **not** commit.  The calling request handler is
responsible for calling ``db.commit()`` — the log entry is persisted in the
same transaction as the surrounding business logic.

Later slices (holds, approvals, cancellations, settings, policies) should
call this function and rely on the surrounding router's commit to persist it.

Signature
---------
    log_activity(
        db,
        *,                  # keyword-only after db
        actor_id,           # int | None  (None = system action)
        action,             # str  e.g. 'user.login', 'bookie.invited', ...
        target_type=None,   # str | None  e.g. 'user', 'farmhouse', 'booking'
        target_id=None,     # int | None
        note=None,          # str | None  free-text annotation
    ) -> ActivityLog
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.activity import ActivityLog


def log_activity(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    note: str | None = None,
) -> ActivityLog:
    """Append an audit entry.

    Adds the row and flushes to assign ``entry.id``.
    The *caller* must commit the session to persist the row.
    """
    entry = ActivityLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        note=note,
    )
    db.add(entry)
    db.flush()
    return entry
