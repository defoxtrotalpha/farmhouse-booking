"""Notification service — fan-out helper for in-app and critical email delivery.

Public API
----------
notify(db, *, recipient_id, type, title, body, booking_id) -> Notification
    Add one row; ADDS+FLUSHES (caller commits).

notify_admins(db, *, type, title, body, booking_id, exclude_user_id) -> list[Notification]
    Fan out to every active admin; optionally exclude one user.

send_critical_email(recipients, subject, body) -> None
    Non-blocking; catches all exceptions (never raises).

dispatch_booking_event(db, *, type, booking, actor_id, critical) -> list[Notification]
    Create in-app notifications for all active admins + booking.bookie_id,
    EXCLUDING the actor. If critical=True also emails all recipients.
    Deduplication: a recipient who is both admin and the bookie receives
    exactly one notification (set-based fan-out).

generate_upcoming_reminders(db, now, within_hours) -> int
    Idempotent: create 'booking.reminder' notifications for booked bookings
    starting within the given window (default 24 h). Returns count created.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("app.notifications")

# Imported at module level so tests can patch app.services.notifications.get_email_sender
from app.services.email import EmailMessage, get_email_sender  # noqa: E402

# ---------------------------------------------------------------------------
# Critical event types — these also trigger email delivery.
# ---------------------------------------------------------------------------

CRITICAL_TYPES: frozenset[str] = frozenset(
    {
        "hold.created",
        "request.submitted",
        "booking.approved",
        "request.rejected",
        "booking.canceled",
        "booking.cancel_requested",
        "booking.cancel_confirmed",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event_title(event_type: str, booking_id: int, bookie_name: str = "") -> str:
    who = f" by {bookie_name}" if bookie_name else ""
    _titles: dict[str, str] = {
        "hold.created":             f"Hold placed{who} — booking #{booking_id}",
        "request.submitted":        f"Booking request{who} — #{booking_id}",
        "booking.approved":         f"Booking #{booking_id} confirmed",
        "request.rejected":         f"Booking #{booking_id} declined",
        "booking.canceled":         f"Booking #{booking_id} canceled",
        "booking.withdrawn":        f"Booking #{booking_id} withdrawn{who}",
        "booking.cancel_requested": f"Cancellation requested — booking #{booking_id}",
        "booking.cancel_confirmed": f"Booking #{booking_id} cancellation confirmed",
        "booking.reminder":         f"Reminder: booking #{booking_id} starts soon",
    }
    return _titles.get(event_type, f"Booking update (#{booking_id})")


# ---------------------------------------------------------------------------
# Core primitives
# ---------------------------------------------------------------------------

def notify(
    db: "Session",
    *,
    recipient_id: int,
    type: str,
    title: str,
    body: str | None = None,
    booking_id: int | None = None,
):
    """Create one notification row.

    ADDS + FLUSHES only; the caller is responsible for committing the session
    (same pattern as log_activity so both land in the same transaction).
    """
    from app.models.notification import Notification

    n = Notification(
        recipient_id=recipient_id,
        type=type,
        title=title,
        body=body,
        booking_id=booking_id,
    )
    db.add(n)
    db.flush()
    return n


def notify_admins(
    db: "Session",
    *,
    type: str,
    title: str,
    body: str | None = None,
    booking_id: int | None = None,
    exclude_user_id: int | None = None,
) -> list:
    """Fan out one notification to every active admin.

    Skips the user identified by *exclude_user_id* (typically the actor).
    Inactive admins are never notified.
    """
    from app.models.user import User

    admins = (
        db.query(User)
        .filter(User.role == "admin", User.is_active == True)  # noqa: E712
        .all()
    )
    notifications = []
    for admin in admins:
        if exclude_user_id is not None and admin.id == exclude_user_id:
            continue
        n = notify(
            db,
            recipient_id=admin.id,
            type=type,
            title=title,
            body=body,
            booking_id=booking_id,
        )
        notifications.append(n)
    return notifications


# ---------------------------------------------------------------------------
# Email helper
# ---------------------------------------------------------------------------

def send_critical_email(recipients: list, subject: str, body: str) -> None:
    """Attempt to email each recipient.  Non-blocking — catches all exceptions."""
    for user in recipients:
        try:
            sender = get_email_sender()
            sender.send(EmailMessage(to=[user.email], subject=subject, body=body))
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to send critical email to %s",
                getattr(user, "email", "?"),
            )


# ---------------------------------------------------------------------------
# Booking-event dispatcher
# ---------------------------------------------------------------------------

def dispatch_booking_event(
    db: "Session",
    *,
    type: str,
    booking,
    actor_id: int,
    critical: bool,
) -> list:
    """Fan out in-app notifications (and optionally emails) for a booking event.

    Recipients = all active admins UNION {booking.bookie_id}, MINUS {actor_id}.

    Deduplication is implicit: using a set of IDs ensures an admin who is also
    the bookie receives exactly one notification.

    If *critical* is True, also calls send_critical_email for all recipients.
    Email failures are suppressed — they never block the business action.
    """
    from app.models.user import User

    # ── collect active admins scoped to the booking's company ─────────────────
    admins = (
        db.query(User)
        .filter(
            User.role == "admin",
            User.is_active == True,  # noqa: E712
            User.tenant_id == booking.tenant_id,
        )
        .all()
    )
    admin_map: dict[int, User] = {a.id: a for a in admins}

    # ── bookie context for human-readable notification titles ─────────────────
    bookie_user: User | None = db.get(User, booking.bookie_id)
    bookie_label = (
        (bookie_user.name or bookie_user.email or f"User #{booking.bookie_id}")
        if bookie_user
        else f"User #{booking.bookie_id}"
    )

    # ── deduped recipient set: admins + bookie, excluding the actor ───────────
    recipient_ids: set[int] = set(admin_map.keys())
    recipient_ids.add(booking.bookie_id)
    recipient_ids.discard(actor_id)

    title = _event_title(type, booking.id, bookie_label)

    # ── build user lookup for email delivery ──────────────────────────────────
    user_map: dict[int, User] = dict(admin_map)
    if booking.bookie_id not in user_map and bookie_user:
        user_map[booking.bookie_id] = bookie_user

    # ── create in-app notifications ───────────────────────────────────────────
    notifications = []
    email_recipients: list[User] = []
    for rid in recipient_ids:
        n = notify(db, recipient_id=rid, type=type, title=title, booking_id=booking.id)
        notifications.append(n)
        if rid in user_map:
            email_recipients.append(user_map[rid])

    # ── optional email dispatch (non-blocking) ────────────────────────────────
    if critical and email_recipients:
        send_critical_email(email_recipients, subject=title, body=title)

    return notifications


# ---------------------------------------------------------------------------
# Upcoming-booking reminder generator
# ---------------------------------------------------------------------------

def generate_upcoming_reminders(
    db: "Session",
    now: datetime | None = None,
    within_hours: int = 24,
) -> int:
    """Create 'booking.reminder' notifications for booked bookings starting soon.

    Idempotent: a booking that already has a reminder notification for its
    bookie will be skipped.  Returns the count of new notifications created.

    Callers that need a different horizon (e.g. tests) can pass *within_hours*.
    The APScheduler job calls this with default args.
    """
    from app.models.booking import Booking
    from app.models.notification import Notification

    if now is None:
        now = datetime.now(timezone.utc)

    cutoff = now + timedelta(hours=within_hours)

    bookings = (
        db.query(Booking)
        .filter(
            Booking.status == "booked",
            Booking.start_at > now,
            Booking.start_at <= cutoff,
        )
        .all()
    )

    count = 0
    for booking in bookings:
        # Idempotency check: skip if a reminder already exists for this bookie+booking
        existing = (
            db.query(Notification)
            .filter(
                Notification.type == "booking.reminder",
                Notification.booking_id == booking.id,
                Notification.recipient_id == booking.bookie_id,
            )
            .first()
        )
        if existing is not None:
            continue

        title = f"Upcoming booking #{booking.id} starts soon"
        notify(
            db,
            recipient_id=booking.bookie_id,
            type="booking.reminder",
            title=title,
            booking_id=booking.id,
        )
        count += 1

    db.commit()
    return count
