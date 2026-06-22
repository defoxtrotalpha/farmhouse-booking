"""Notifications — TDD vertical slice (#27).

TDD order:
  RED-1  : notify() creates one row for the specified recipient
  RED-2  : notify_admins() fans out to ALL active admins; skips inactive admin
  RED-3  : notify_admins() exclude_user_id skips that admin
  RED-4  : dispatch_booking_event request.submitted -> admins notified, bookie (actor) excluded
  RED-5  : dispatch_booking_event booking.approved -> bookie + other admins notified, acting admin excluded
  RED-6  : dispatch_booking_event dedupe: bookie who is also admin gets exactly one notification
  RED-7  : GET /api/notifications returns only current user's notifications (other user's invisible)
  RED-8  : GET /api/notifications?unread=true returns only unread
  RED-9  : GET /api/notifications/unread-count returns correct count
  RED-10 : POST /api/notifications/{id}/read flips is_read to True; returns notification
  RED-11 : POST /api/notifications/read-all marks all my unread notifications read
  RED-12 : POST /api/notifications/{id}/read on someone else's -> 404
  RED-13 : Critical event (dispatch_booking_event critical=True) sends email via get_email_sender
  RED-14 : Non-critical event (critical=False) does NOT call email sender
  RED-15 : Email failure (sender.send raises) does not block; in-app notification still persisted
  RED-16 : generate_upcoming_reminders creates reminder for booked booking starting in 6h
  RED-17 : generate_upcoming_reminders is idempotent — second call returns 0
  RED-18 : generate_upcoming_reminders ignores bookings outside the window
  RED-19 : generate_upcoming_reminders ignores non-booked bookings
  RED-20 : Integration: POST /api/bookings/{id}/submit creates request.submitted notifications for admins
  RED-21 : Integration: POST /api/bookings/{id}/approve creates booking.approved notification for bookie
  RED-22 : Integration: POST /api/bookings/{id}/reject creates request.rejected notification for bookie
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Shared DB/client factory helpers
# ---------------------------------------------------------------------------

def _make_client() -> TestClient:
    """Fresh isolated in-memory SQLite TestClient."""
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa — populates Base.metadata

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    c = TestClient(application)
    c._db_session = TestSession  # type: ignore[attr-defined]
    return c


def _make_db():
    """Return a bare (session_factory, session) pair — no HTTP layer needed."""
    from app.db import Base
    import app.models  # noqa

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    return TestSession, TestSession()


def _seed_users(session_factory, *, n_admins: int = 1, n_bookies: int = 1):
    """Seed admin(s) + bookie(s).  Returns (tokens_dict, ids_dict)."""
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    admins, bookies = [], []
    for i in range(n_admins):
        u = User(
            email=f"admin{i}@notif-test.com",
            name=f"Admin{i}",
            password_hash=hash_password("pass"),
            role="admin",
            is_active=True,
        )
        db.add(u)
        admins.append(u)
    for i in range(n_bookies):
        u = User(
            email=f"bk{i}@notif-test.com",
            name=f"Bookie{i}",
            password_hash=hash_password("pass"),
            role="bookie",
            is_active=True,
        )
        db.add(u)
        bookies.append(u)
    db.commit()
    for u in admins + bookies:
        db.refresh(u)

    tokens = {}
    ids = {}
    for u in admins + bookies:
        tok = create_access_token(user_id=u.id, role=u.role)
        tokens[u.email] = f"Bearer {tok}"
        ids[u.email] = u.id
    db.close()
    return tokens, ids


def _seed_farmhouse(session_factory) -> int:
    from app.models.farmhouse import Farmhouse

    db = session_factory()
    fh = Farmhouse(name="Notif Test FH", status="active", buffer_minutes=0)
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fh_id = fh.id
    db.close()
    return fh_id


def _future(hours: float = 25) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _hold_body(fh_id: int) -> dict:
    start = _future(25)
    end = start + timedelta(hours=2)
    return {
        "farmhouse_id": fh_id,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
    }


def _submit_body() -> dict:
    return {
        "client_name": "Test Client",
        "client_contact": "test@client.com",
        "event_type": "party",
        "event_info": None,
        "notes": None,
        "quoted_price": None,
    }


# ---------------------------------------------------------------------------
# RED-1: notify() creates one row for the recipient
# ---------------------------------------------------------------------------

def test_notify_creates_row():
    from app.services.notifications import notify
    from app.models.notification import Notification

    _, db = _make_db()
    from app.models.user import User
    from app.security import hash_password

    u = User(email="a@t.com", name="A", password_hash=hash_password("x"), role="bookie", is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)

    n = notify(db, recipient_id=u.id, type="booking.approved", title="Approved", booking_id=None)
    db.commit()

    rows = db.query(Notification).all()
    assert len(rows) == 1
    assert rows[0].recipient_id == u.id
    assert rows[0].type == "booking.approved"
    assert rows[0].is_read is False


# ---------------------------------------------------------------------------
# RED-2: notify_admins() fans out to active admins; skips inactive
# ---------------------------------------------------------------------------

def test_notify_admins_fans_out_skips_inactive():
    from app.services.notifications import notify_admins
    from app.models.notification import Notification
    from app.models.user import User
    from app.security import hash_password

    _, db = _make_db()
    admin_active = User(email="active@t.com", name="A", password_hash=hash_password("x"), role="admin", is_active=True)
    admin_inactive = User(email="inactive@t.com", name="I", password_hash=hash_password("x"), role="admin", is_active=False)
    bookie = User(email="bk@t.com", name="B", password_hash=hash_password("x"), role="bookie", is_active=True)
    db.add_all([admin_active, admin_inactive, bookie])
    db.commit()
    for u in [admin_active, admin_inactive, bookie]:
        db.refresh(u)

    notifs = notify_admins(db, type="request.submitted", title="New request")
    db.commit()

    rows = db.query(Notification).all()
    recipient_ids = {r.recipient_id for r in rows}
    assert admin_active.id in recipient_ids
    assert admin_inactive.id not in recipient_ids  # inactive skipped
    assert bookie.id not in recipient_ids          # bookie not an admin


# ---------------------------------------------------------------------------
# RED-3: notify_admins() exclude_user_id skips that admin
# ---------------------------------------------------------------------------

def test_notify_admins_exclude_user():
    from app.services.notifications import notify_admins
    from app.models.notification import Notification
    from app.models.user import User
    from app.security import hash_password

    _, db = _make_db()
    a1 = User(email="a1@t.com", name="A1", password_hash=hash_password("x"), role="admin", is_active=True)
    a2 = User(email="a2@t.com", name="A2", password_hash=hash_password("x"), role="admin", is_active=True)
    db.add_all([a1, a2])
    db.commit()
    db.refresh(a1); db.refresh(a2)

    notify_admins(db, type="hold.created", title="Hold", exclude_user_id=a1.id)
    db.commit()

    rows = db.query(Notification).all()
    recipient_ids = {r.recipient_id for r in rows}
    assert a1.id not in recipient_ids   # excluded
    assert a2.id in recipient_ids


# ---------------------------------------------------------------------------
# RED-4: dispatch_booking_event request.submitted — admins notified, bookie (actor) excluded
# ---------------------------------------------------------------------------

def test_dispatch_submit_admins_not_bookie():
    from app.services.notifications import dispatch_booking_event
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()
    admin = User(email="ad@t.com", name="Ad", password_hash=hash_password("x"), role="admin", is_active=True)
    bookie = User(email="bk@t.com", name="Bk", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([admin, bookie, fh])
    db.commit()
    for o in [admin, bookie, fh]:
        db.refresh(o)

    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="pending",
        start_at=_future(25),
        end_at=_future(27),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Bookie submits (actor = bookie)
    dispatch_booking_event(db, type="request.submitted", booking=booking, actor_id=bookie.id, critical=False)
    db.commit()

    rows = db.query(Notification).all()
    recipient_ids = {r.recipient_id for r in rows}
    assert admin.id in recipient_ids        # admin notified
    assert bookie.id not in recipient_ids   # bookie is actor → excluded


# ---------------------------------------------------------------------------
# RED-5: dispatch_booking_event booking.approved — bookie + other admins notified
# ---------------------------------------------------------------------------

def test_dispatch_approve_notifies_bookie_and_admins():
    from app.services.notifications import dispatch_booking_event
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()
    admin = User(email="admin@t.com", name="Admin", password_hash=hash_password("x"), role="admin", is_active=True)
    admin2 = User(email="admin2@t.com", name="Admin2", password_hash=hash_password("x"), role="admin", is_active=True)
    bookie = User(email="bk@t.com", name="Bk", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([admin, admin2, bookie, fh])
    db.commit()
    for o in [admin, admin2, bookie, fh]:
        db.refresh(o)

    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="booked",
        start_at=_future(25),
        end_at=_future(27),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Admin approves (actor = admin)
    dispatch_booking_event(db, type="booking.approved", booking=booking, actor_id=admin.id, critical=False)
    db.commit()

    rows = db.query(Notification).all()
    recipient_ids = {r.recipient_id for r in rows}
    assert bookie.id in recipient_ids    # bookie notified
    assert admin2.id in recipient_ids    # other admin notified
    assert admin.id not in recipient_ids # acting admin excluded


# ---------------------------------------------------------------------------
# RED-6: dedupe — admin who is also the bookie gets exactly one notification
# ---------------------------------------------------------------------------

def test_dispatch_dedupe_admin_bookie():
    from app.services.notifications import dispatch_booking_event
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()
    # This user is BOTH admin AND the booking's bookie
    admin_bookie = User(email="ab@t.com", name="AB", password_hash=hash_password("x"), role="admin", is_active=True)
    other_admin = User(email="oa@t.com", name="OA", password_hash=hash_password("x"), role="admin", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([admin_bookie, other_admin, fh])
    db.commit()
    for o in [admin_bookie, other_admin, fh]:
        db.refresh(o)

    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=admin_bookie.id,  # admin IS the bookie
        status="booked",
        start_at=_future(25),
        end_at=_future(27),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # other_admin is the actor; admin_bookie should receive ONE notification (not two)
    dispatch_booking_event(db, type="booking.approved", booking=booking, actor_id=other_admin.id, critical=False)
    db.commit()

    rows = db.query(Notification).filter(Notification.recipient_id == admin_bookie.id).all()
    assert len(rows) == 1   # exactly one despite being both admin and bookie


# ---------------------------------------------------------------------------
# Endpoint helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def notif_client():
    c = _make_client()
    tokens, ids = _seed_users(c._db_session, n_admins=1, n_bookies=1)
    c._tokens = tokens  # type: ignore[attr-defined]
    c._ids = ids        # type: ignore[attr-defined]
    return c


def _auth(c, email) -> dict:
    return {"Authorization": c._tokens[email]}


# ---------------------------------------------------------------------------
# RED-7: GET /api/notifications isolation — only my own notifications
# ---------------------------------------------------------------------------

def test_list_notifications_isolation(notif_client):
    c = notif_client
    from app.services.notifications import notify
    from app.models.notification import Notification

    admin_id  = c._ids["admin0@notif-test.com"]
    bookie_id = c._ids["bk0@notif-test.com"]

    db = c._db_session()
    notify(db, recipient_id=admin_id,  type="booking.approved", title="For Admin")
    notify(db, recipient_id=bookie_id, type="booking.approved", title="For Bookie")
    db.commit()
    db.close()

    # Admin sees only their own
    res = c.get("/api/notifications", headers=_auth(c, "admin0@notif-test.com"))
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "For Admin"

    # Bookie sees only their own
    res2 = c.get("/api/notifications", headers=_auth(c, "bk0@notif-test.com"))
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2) == 1
    assert data2[0]["title"] == "For Bookie"


# ---------------------------------------------------------------------------
# RED-8: unread filter
# ---------------------------------------------------------------------------

def test_list_notifications_unread_filter(notif_client):
    c = notif_client
    from app.services.notifications import notify
    from app.models.notification import Notification

    admin_id = c._ids["admin0@notif-test.com"]

    db = c._db_session()
    n_unread = notify(db, recipient_id=admin_id, type="hold.created",  title="Unread")
    n_read   = notify(db, recipient_id=admin_id, type="booking.approved", title="Read")
    db.flush()
    n_read.is_read = True
    db.commit()
    db.close()

    res = c.get("/api/notifications?unread=true", headers=_auth(c, "admin0@notif-test.com"))
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Unread"

    res2 = c.get("/api/notifications?unread=false", headers=_auth(c, "admin0@notif-test.com"))
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2) == 1
    assert data2[0]["title"] == "Read"


# ---------------------------------------------------------------------------
# RED-9: unread-count
# ---------------------------------------------------------------------------

def test_unread_count(notif_client):
    c = notif_client
    from app.services.notifications import notify

    admin_id = c._ids["admin0@notif-test.com"]

    db = c._db_session()
    notify(db, recipient_id=admin_id, type="hold.created", title="A")
    notify(db, recipient_id=admin_id, type="hold.created", title="B")
    db.commit()
    db.close()

    res = c.get("/api/notifications/unread-count", headers=_auth(c, "admin0@notif-test.com"))
    assert res.status_code == 200
    assert res.json()["count"] == 2


# ---------------------------------------------------------------------------
# RED-10: POST /{id}/read flips is_read; returns notification
# ---------------------------------------------------------------------------

def test_mark_read(notif_client):
    c = notif_client
    from app.services.notifications import notify

    admin_id = c._ids["admin0@notif-test.com"]

    db = c._db_session()
    n = notify(db, recipient_id=admin_id, type="booking.approved", title="For me")
    db.commit()
    notif_id = n.id
    db.close()

    res = c.post(f"/api/notifications/{notif_id}/read", headers=_auth(c, "admin0@notif-test.com"))
    assert res.status_code == 200
    data = res.json()
    assert data["is_read"] is True
    assert data["id"] == notif_id


# ---------------------------------------------------------------------------
# RED-11: POST /read-all marks all unread as read
# ---------------------------------------------------------------------------

def test_mark_all_read(notif_client):
    c = notif_client
    from app.services.notifications import notify

    admin_id = c._ids["admin0@notif-test.com"]

    db = c._db_session()
    notify(db, recipient_id=admin_id, type="hold.created", title="A")
    notify(db, recipient_id=admin_id, type="hold.created", title="B")
    notify(db, recipient_id=admin_id, type="hold.created", title="C")
    db.commit()
    db.close()

    res = c.post("/api/notifications/read-all", headers=_auth(c, "admin0@notif-test.com"))
    assert res.status_code == 200
    assert res.json()["updated"] == 3

    # All now read
    res2 = c.get("/api/notifications/unread-count", headers=_auth(c, "admin0@notif-test.com"))
    assert res2.json()["count"] == 0


# ---------------------------------------------------------------------------
# RED-12: POST /{id}/read on someone else's notification -> 404
# ---------------------------------------------------------------------------

def test_mark_read_other_user_404(notif_client):
    c = notif_client
    from app.services.notifications import notify

    bookie_id = c._ids["bk0@notif-test.com"]

    db = c._db_session()
    n = notify(db, recipient_id=bookie_id, type="booking.approved", title="For Bookie")
    db.commit()
    notif_id = n.id
    db.close()

    # Admin tries to mark BOOKIE's notification as read → 404
    res = c.post(f"/api/notifications/{notif_id}/read", headers=_auth(c, "admin0@notif-test.com"))
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# RED-13: Critical event calls get_email_sender (via dispatch_booking_event)
# ---------------------------------------------------------------------------

def test_critical_event_sends_email(monkeypatch):
    from app.services import notifications as notif_mod
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()

    class CapturingSender:
        def __init__(self):
            self.sent = []
        def send(self, msg):
            self.sent.append(msg)
            return True

    capturing = CapturingSender()
    monkeypatch.setattr(notif_mod, "get_email_sender", lambda: capturing)

    admin = User(email="admin@t.com", name="A", password_hash=hash_password("x"), role="admin", is_active=True)
    bookie = User(email="bk@t.com", name="B", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([admin, bookie, fh])
    db.commit()
    for o in [admin, bookie, fh]:
        db.refresh(o)

    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="booked",
        start_at=_future(25),
        end_at=_future(27),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    notif_mod.dispatch_booking_event(
        db, type="booking.approved", booking=booking, actor_id=admin.id, critical=True
    )
    db.commit()

    # bookie must have received an email (admin is actor, excluded)
    assert len(capturing.sent) >= 1
    all_to = [addr for msg in capturing.sent for addr in msg.to]
    assert "bk@t.com" in all_to


# ---------------------------------------------------------------------------
# RED-14: Non-critical event does NOT email
# ---------------------------------------------------------------------------

def test_non_critical_no_email(monkeypatch):
    from app.services import notifications as notif_mod
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()

    class CapturingSender:
        def __init__(self):
            self.sent = []
        def send(self, msg):
            self.sent.append(msg)
            return True

    capturing = CapturingSender()
    monkeypatch.setattr(notif_mod, "get_email_sender", lambda: capturing)

    admin = User(email="admin@t.com", name="A", password_hash=hash_password("x"), role="admin", is_active=True)
    bookie = User(email="bk@t.com", name="B", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([admin, bookie, fh])
    db.commit()
    for o in [admin, bookie, fh]:
        db.refresh(o)

    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="canceled",
        start_at=_future(25),
        end_at=_future(27),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    notif_mod.dispatch_booking_event(
        db, type="booking.withdrawn", booking=booking, actor_id=bookie.id, critical=False
    )
    db.commit()

    assert len(capturing.sent) == 0  # non-critical → no email


# ---------------------------------------------------------------------------
# RED-15: Email failure doesn't block; in-app notification still persisted
# ---------------------------------------------------------------------------

def test_email_failure_does_not_block(monkeypatch):
    from app.services import notifications as notif_mod
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()

    class FailingSender:
        def send(self, msg):
            raise RuntimeError("SMTP exploded")

    monkeypatch.setattr(notif_mod, "get_email_sender", lambda: FailingSender())

    admin = User(email="admin@t.com", name="A", password_hash=hash_password("x"), role="admin", is_active=True)
    bookie = User(email="bk@t.com", name="B", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([admin, bookie, fh])
    db.commit()
    for o in [admin, bookie, fh]:
        db.refresh(o)

    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="booked",
        start_at=_future(25),
        end_at=_future(27),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Should NOT raise even though email fails
    notif_mod.dispatch_booking_event(
        db, type="booking.approved", booking=booking, actor_id=admin.id, critical=True
    )
    db.commit()

    # In-app notification for bookie must still be in DB
    rows = db.query(Notification).filter(Notification.recipient_id == bookie.id).all()
    assert len(rows) >= 1


# ---------------------------------------------------------------------------
# RED-16: generate_upcoming_reminders creates reminder for booking starting in 6h
# ---------------------------------------------------------------------------

def test_reminders_creates_for_upcoming():
    from app.services.notifications import generate_upcoming_reminders
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()
    bookie = User(email="bk@t.com", name="B", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([bookie, fh])
    db.commit()
    db.refresh(bookie); db.refresh(fh)

    now = datetime.now(timezone.utc)
    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="booked",
        start_at=now + timedelta(hours=6),
        end_at=now + timedelta(hours=8),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    count = generate_upcoming_reminders(db, now=now, within_hours=24)
    assert count == 1

    rows = db.query(Notification).filter(
        Notification.type == "booking.reminder",
        Notification.booking_id == booking.id,
        Notification.recipient_id == bookie.id,
    ).all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# RED-17: generate_upcoming_reminders is idempotent
# ---------------------------------------------------------------------------

def test_reminders_idempotent():
    from app.services.notifications import generate_upcoming_reminders
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()
    bookie = User(email="bk@t.com", name="B", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([bookie, fh])
    db.commit()
    db.refresh(bookie); db.refresh(fh)

    now = datetime.now(timezone.utc)
    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="booked",
        start_at=now + timedelta(hours=6),
        end_at=now + timedelta(hours=8),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    first  = generate_upcoming_reminders(db, now=now, within_hours=24)
    second = generate_upcoming_reminders(db, now=now, within_hours=24)

    assert first  == 1
    assert second == 0  # idempotent — no duplicate

    rows = db.query(Notification).filter(Notification.type == "booking.reminder").all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# RED-18: generate_upcoming_reminders ignores bookings outside the window
# ---------------------------------------------------------------------------

def test_reminders_ignores_outside_window():
    from app.services.notifications import generate_upcoming_reminders
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()
    bookie = User(email="bk@t.com", name="B", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([bookie, fh])
    db.commit()
    db.refresh(bookie); db.refresh(fh)

    now = datetime.now(timezone.utc)
    # Booking starts 30h from now — outside the 24h window
    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="booked",
        start_at=now + timedelta(hours=30),
        end_at=now + timedelta(hours=32),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    count = generate_upcoming_reminders(db, now=now, within_hours=24)
    assert count == 0

    rows = db.query(Notification).all()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# RED-19: generate_upcoming_reminders ignores non-booked bookings
# ---------------------------------------------------------------------------

def test_reminders_ignores_non_booked():
    from app.services.notifications import generate_upcoming_reminders
    from app.models.notification import Notification
    from app.models.user import User
    from app.models.farmhouse import Farmhouse
    from app.models.booking import Booking
    from app.security import hash_password

    _, db = _make_db()
    bookie = User(email="bk@t.com", name="B", password_hash=hash_password("x"), role="bookie", is_active=True)
    fh = Farmhouse(name="FH", status="active", buffer_minutes=0)
    db.add_all([bookie, fh])
    db.commit()
    db.refresh(bookie); db.refresh(fh)

    now = datetime.now(timezone.utc)
    # Pending booking — should NOT get a reminder
    booking = Booking(
        farmhouse_id=fh.id,
        bookie_id=bookie.id,
        status="pending",
        start_at=now + timedelta(hours=6),
        end_at=now + timedelta(hours=8),
        buffer_minutes_snapshot=0,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    count = generate_upcoming_reminders(db, now=now, within_hours=24)
    assert count == 0

    rows = db.query(Notification).all()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------

def _make_integration_client():
    """Client with admin + bookie + farmhouse pre-seeded."""
    c = _make_client()
    tokens, ids = _seed_users(c._db_session, n_admins=1, n_bookies=1)
    fh_id = _seed_farmhouse(c._db_session)
    c._tokens = tokens  # type: ignore[attr-defined]
    c._ids = ids        # type: ignore[attr-defined]
    c._fh_id = fh_id    # type: ignore[attr-defined]
    return c


def _create_hold_and_submit(c) -> int:
    """Place a hold and submit it; return booking_id."""
    admin_email = "admin0@notif-test.com"
    bookie_email = "bk0@notif-test.com"
    bk_tok = c._tokens[bookie_email]

    res = c.post("/api/bookings/hold", json=_hold_body(c._fh_id), headers={"Authorization": bk_tok})
    assert res.status_code == 201
    booking_id = res.json()["id"]

    res2 = c.post(f"/api/bookings/{booking_id}/submit", json=_submit_body(), headers={"Authorization": bk_tok})
    assert res2.status_code == 200
    return booking_id


# ---------------------------------------------------------------------------
# RED-20: POST /api/bookings/{id}/submit creates request.submitted notifications for admins
# ---------------------------------------------------------------------------

def test_integration_submit_notifies_admins():
    c = _make_integration_client()
    from app.models.notification import Notification

    # Clear any hold.created notifications first
    db = c._db_session()

    booking_id = _create_hold_and_submit(c)

    admin_id  = c._ids["admin0@notif-test.com"]
    bookie_id = c._ids["bk0@notif-test.com"]

    rows = db.query(Notification).filter(Notification.type == "request.submitted").all()
    recipient_ids = {r.recipient_id for r in rows}

    assert admin_id  in recipient_ids   # admin notified
    assert bookie_id not in recipient_ids  # bookie is actor, not notified
    db.close()


# ---------------------------------------------------------------------------
# RED-21: POST /api/bookings/{id}/approve creates booking.approved notification for bookie
# ---------------------------------------------------------------------------

def test_integration_approve_notifies_bookie():
    c = _make_integration_client()
    from app.models.notification import Notification

    booking_id = _create_hold_and_submit(c)

    admin_tok  = c._tokens["admin0@notif-test.com"]
    bookie_id  = c._ids["bk0@notif-test.com"]

    res = c.post(f"/api/bookings/{booking_id}/approve", headers={"Authorization": admin_tok})
    assert res.status_code == 200

    db = c._db_session()
    rows = db.query(Notification).filter(Notification.type == "booking.approved").all()
    recipient_ids = {r.recipient_id for r in rows}
    assert bookie_id in recipient_ids
    db.close()


# ---------------------------------------------------------------------------
# RED-22: POST /api/bookings/{id}/reject creates request.rejected notification for bookie
# ---------------------------------------------------------------------------

def test_integration_reject_notifies_bookie():
    c = _make_integration_client()
    from app.models.notification import Notification

    booking_id = _create_hold_and_submit(c)

    admin_tok  = c._tokens["admin0@notif-test.com"]
    bookie_id  = c._ids["bk0@notif-test.com"]

    res = c.post(
        f"/api/bookings/{booking_id}/reject",
        json={"reason": "No availability"},
        headers={"Authorization": admin_tok},
    )
    assert res.status_code == 200

    db = c._db_session()
    rows = db.query(Notification).filter(Notification.type == "request.rejected").all()
    recipient_ids = {r.recipient_id for r in rows}
    assert bookie_id in recipient_ids
    db.close()
