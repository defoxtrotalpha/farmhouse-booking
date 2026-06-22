"""Hold expiry — TDD vertical slice (#25).

TDD order:
  RED-1 : is_hold_expired True  — status='hold', expires_at in the past
  RED-2 : is_hold_expired False — status='hold', expires_at in the future (fresh)
  RED-3 : is_hold_expired False — status='pending', expires_at in the past (wrong status)
  RED-4 : is_hold_expired False — status='hold', expires_at is None
  RED-5 : expire_stale_holds flips stale holds to 'expired', returns count
  RED-6 : expire_stale_holds ignores fresh holds, pending, booked
  RED-7 : availability EXCLUDES expired hold (expires_at < now, status still 'hold')
  RED-8 : availability INCLUDES fresh hold (expires_at > now)
  RED-9 : GET /api/bookings excludes expired-by-time hold from active listing
  RED-10: POST /api/bookings/{id}/submit on expired hold -> 409 "Hold has expired..."
  RED-11: POST /api/bookings/{id}/submit on fresh hold still succeeds -> 200
  RED-12: POST /api/bookings/hold expires_at matches settings.hold_duration_hours
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared helpers  (identical pattern to test_booking_hold.py)
# ---------------------------------------------------------------------------

def _make_client() -> TestClient:
    """Fresh TestClient backed by an isolated in-memory SQLite DB."""
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa — registers ALL models with Base.metadata

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


def _seed_users(session_factory):
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    admin   = User(email="admin@exp-test.com",  name="Admin",   password_hash=hash_password("pass"), role="admin",  is_active=True)
    bookie1 = User(email="bk1@exp-test.com",    name="Bookie1", password_hash=hash_password("pass"), role="bookie", is_active=True)
    db.add_all([admin, bookie1])
    db.commit()
    db.refresh(admin); db.refresh(bookie1)

    at_admin = create_access_token(user_id=admin.id, role="admin")
    at_bk1   = create_access_token(user_id=bookie1.id, role="bookie")
    db.close()
    return (
        (f"Bearer {at_admin}", f"Bearer {at_bk1}"),
        (admin.id, bookie1.id),
    )


def _seed_farmhouse(session_factory) -> int:
    from app.models.farmhouse import Farmhouse

    db = session_factory()
    fh = Farmhouse(name="Expiry Test FH", status="active", buffer_minutes=0)
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fh_id = fh.id
    db.close()
    return fh_id


def _seed_booking(session_factory, *, bookie_id: int, fh_id: int, status: str,
                  expires_at: datetime | None) -> int:
    """Insert a booking row directly (bypassing the API) for unit-level tests."""
    from app.models.booking import Booking

    now = datetime.now(timezone.utc)
    db = session_factory()
    b = Booking(
        farmhouse_id=fh_id,
        bookie_id=bookie_id,
        status=status,
        start_at=now + timedelta(hours=25),
        end_at=now + timedelta(hours=27),
        buffer_minutes_snapshot=0,
        expires_at=expires_at,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    bid = b.id
    db.close()
    return bid


def _future(hours: float = 25) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _past(hours: float = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _hold_body(fh_id: int, *, start_offset_h: float = 25, duration_h: float = 2) -> dict:
    start = _future(start_offset_h)
    end   = start + timedelta(hours=duration_h)
    return {
        "farmhouse_id": fh_id,
        "start_at": start.isoformat(),
        "end_at":   end.isoformat(),
    }


def _submit_body() -> dict:
    return {
        "client_name": "Test Client",
        "client_contact": "test@client.com",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def expiry_client():
    c = _make_client()
    (admin_tok, bk1_tok), (admin_id, bk1_id) = _seed_users(c._db_session)
    c._admin_token  = admin_tok   # type: ignore[attr-defined]
    c._bookie_token = bk1_tok     # type: ignore[attr-defined]
    c._admin_id     = admin_id    # type: ignore[attr-defined]
    c._bookie_id    = bk1_id      # type: ignore[attr-defined]
    c._fh_id = _seed_farmhouse(c._db_session)  # type: ignore[attr-defined]
    return c


# ---------------------------------------------------------------------------
# RED-1: is_hold_expired True when status='hold' and expires_at < now
# ---------------------------------------------------------------------------

def test_is_hold_expired_true():
    from app.services.hold_expiry import is_hold_expired

    class FakeBooking:
        status = "hold"
        expires_at = _past(1)  # 1 hour ago

    now = datetime.now(timezone.utc)
    assert is_hold_expired(FakeBooking(), now) is True


# ---------------------------------------------------------------------------
# RED-2: is_hold_expired False when status='hold' and expires_at is in the future
# ---------------------------------------------------------------------------

def test_is_hold_expired_false_fresh_hold():
    from app.services.hold_expiry import is_hold_expired

    class FakeBooking:
        status = "hold"
        expires_at = _future(23)  # still 23 h ahead

    now = datetime.now(timezone.utc)
    assert is_hold_expired(FakeBooking(), now) is False


# ---------------------------------------------------------------------------
# RED-3: is_hold_expired False when status != 'hold' (e.g. pending)
# ---------------------------------------------------------------------------

def test_is_hold_expired_false_wrong_status():
    from app.services.hold_expiry import is_hold_expired

    class FakeBooking:
        status = "pending"
        expires_at = _past(2)  # old timestamp but status is not 'hold'

    now = datetime.now(timezone.utc)
    assert is_hold_expired(FakeBooking(), now) is False


# ---------------------------------------------------------------------------
# RED-4: is_hold_expired False when expires_at is None
# ---------------------------------------------------------------------------

def test_is_hold_expired_false_no_expires_at():
    from app.services.hold_expiry import is_hold_expired

    class FakeBooking:
        status = "hold"
        expires_at = None

    now = datetime.now(timezone.utc)
    assert is_hold_expired(FakeBooking(), now) is False


# ---------------------------------------------------------------------------
# RED-5: expire_stale_holds flips stale holds, returns count
# ---------------------------------------------------------------------------

def test_expire_stale_holds_flips_and_returns_count():
    from app.services.hold_expiry import expire_stale_holds

    c = _make_client()
    _, (_, bk_id) = _seed_users(c._db_session)
    fh_id = _seed_farmhouse(c._db_session)

    # Two stale holds + one fresh hold
    bid_stale1 = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                                status="hold", expires_at=_past(2))
    bid_stale2 = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                                status="hold", expires_at=_past(0.5))
    bid_fresh  = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                                status="hold", expires_at=_future(20))

    from app.models.booking import Booking

    db = c._db_session()
    try:
        now = datetime.now(timezone.utc)
        count = expire_stale_holds(db, now=now)
        assert count == 2

        db.expire_all()
        s1 = db.get(Booking, bid_stale1)
        s2 = db.get(Booking, bid_stale2)
        fresh = db.get(Booking, bid_fresh)
        assert s1.status == "expired"
        assert s2.status == "expired"
        assert fresh.status == "hold"  # untouched
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RED-6: expire_stale_holds does not touch pending / booked / fresh holds
# ---------------------------------------------------------------------------

def test_expire_stale_holds_ignores_non_hold_statuses():
    from app.services.hold_expiry import expire_stale_holds

    c = _make_client()
    _, (_, bk_id) = _seed_users(c._db_session)
    fh_id = _seed_farmhouse(c._db_session)

    bid_pending = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                                 status="pending", expires_at=_past(1))
    bid_booked  = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                                 status="booked", expires_at=_past(1))
    bid_fresh   = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                                 status="hold",  expires_at=_future(10))

    from app.models.booking import Booking

    db = c._db_session()
    try:
        count = expire_stale_holds(db, now=datetime.now(timezone.utc))
        assert count == 0

        db.expire_all()
        assert db.get(Booking, bid_pending).status == "pending"
        assert db.get(Booking, bid_booked).status  == "booked"
        assert db.get(Booking, bid_fresh).status   == "hold"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RED-7: availability EXCLUDES an expired hold (status='hold', expires_at < now)
# ---------------------------------------------------------------------------

def test_availability_excludes_expired_hold(expiry_client):
    c = expiry_client
    bk_id = c._bookie_id
    fh_id = c._fh_id

    # Insert a hold that expired 1 hour ago (not yet swept by scheduler)
    _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                  status="hold", expires_at=_past(1))

    start = (_future(24)).isoformat()
    end   = (_future(28)).isoformat()
    res = c.get(
        f"/api/farmhouses/{fh_id}/availability",
        params={"start": start, "end": end},
        headers={"Authorization": c._bookie_token},
    )
    assert res.status_code == 200
    assert res.json() == [], "Expired hold must not appear as occupied"


# ---------------------------------------------------------------------------
# RED-8: availability INCLUDES a fresh hold (expires_at > now)
# ---------------------------------------------------------------------------

def test_availability_includes_fresh_hold(expiry_client):
    c = expiry_client
    bk_id = c._bookie_id
    fh_id = c._fh_id

    _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                  status="hold", expires_at=_future(20))

    start = (_future(24)).isoformat()
    end   = (_future(28)).isoformat()
    res = c.get(
        f"/api/farmhouses/{fh_id}/availability",
        params={"start": start, "end": end},
        headers={"Authorization": c._bookie_token},
    )
    assert res.status_code == 200
    assert len(res.json()) == 1, "Fresh hold must appear as occupied"


# ---------------------------------------------------------------------------
# RED-9: GET /api/bookings excludes expired-by-time hold from active listing
# ---------------------------------------------------------------------------

def test_list_bookings_excludes_expired_hold(expiry_client):
    c = expiry_client
    bk_id = c._bookie_id
    fh_id = c._fh_id

    # Insert one expired hold + one fresh hold for the same bookie
    _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                  status="hold", expires_at=_past(1))
    bid_fresh = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                               status="hold", expires_at=_future(20))

    res = c.get("/api/bookings", headers={"Authorization": c._bookie_token})
    assert res.status_code == 200
    ids = [b["id"] for b in res.json()]
    assert bid_fresh in ids, "Fresh hold should appear"
    # No expired hold should appear (it still has status='hold' in DB)
    for b in res.json():
        if b["status"] == "hold":
            # parse expires_at and verify it's in the future
            expires_str = b.get("expires_at")
            assert expires_str is not None
            expires = datetime.fromisoformat(expires_str)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            assert expires > datetime.now(timezone.utc), (
                f"Listing must not return expired hold (expires_at={expires})"
            )


# ---------------------------------------------------------------------------
# RED-10: POST /api/bookings/{id}/submit on expired hold -> 409
# ---------------------------------------------------------------------------

def test_submit_expired_hold_returns_409(expiry_client):
    c = expiry_client
    bk_id = c._bookie_id
    fh_id = c._fh_id

    # Insert a hold that expired 2 hours ago
    bid = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                        status="hold", expires_at=_past(2))

    res = c.post(
        f"/api/bookings/{bid}/submit",
        json=_submit_body(),
        headers={"Authorization": c._bookie_token},
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "expired" in detail.lower(), f"Expected 'expired' in detail, got: {detail!r}"
    assert "new hold" in detail.lower() or "place" in detail.lower(), (
        f"Expected re-hold prompt in detail, got: {detail!r}"
    )


# ---------------------------------------------------------------------------
# RED-11: POST /api/bookings/{id}/submit on fresh hold still succeeds -> 200
# ---------------------------------------------------------------------------

def test_submit_fresh_hold_succeeds(expiry_client):
    c = expiry_client
    bk_id = c._bookie_id
    fh_id = c._fh_id

    # Insert a fresh hold (expires in 20 hours)
    bid = _seed_booking(c._db_session, bookie_id=bk_id, fh_id=fh_id,
                        status="hold", expires_at=_future(20))

    res = c.post(
        f"/api/bookings/{bid}/submit",
        json=_submit_body(),
        headers={"Authorization": c._bookie_token},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending"
    assert data["expires_at"] is None  # cleared on submit


# ---------------------------------------------------------------------------
# RED-12: POST /api/bookings/hold: expires_at matches settings.hold_duration_hours
# ---------------------------------------------------------------------------

def test_hold_expires_at_uses_settings_duration(expiry_client):
    """expires_at should be ~settings.hold_duration_hours from now."""
    from app.config import get_settings

    c = expiry_client
    s = get_settings()

    now_before = datetime.now(timezone.utc)
    res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie_token},
    )
    now_after = datetime.now(timezone.utc)
    assert res.status_code == 201

    expires_str = res.json()["expires_at"]
    assert expires_str is not None
    expires = datetime.fromisoformat(expires_str)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    expected_low  = now_before + timedelta(hours=s.hold_duration_hours)
    expected_high = now_after  + timedelta(hours=s.hold_duration_hours)

    assert expected_low <= expires <= expected_high, (
        f"expires_at {expires} not in expected window "
        f"[{expected_low}, {expected_high}] for hold_duration_hours={s.hold_duration_hours}"
    )
