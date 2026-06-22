"""Settings, blackout dates & business rules — TDD vertical slice #29.

TDD order:
  RED-1  : get_or_create_settings creates singleton with defaults (id=1)
  RED-2  : get_or_create_settings idempotent (second call returns same row)
  RED-3  : GET /api/settings returns settings (any active user)
  RED-4  : GET /api/settings unauthenticated -> 401
  RED-5  : PATCH /api/settings by admin updates fields -> 200
  RED-6  : PATCH /api/settings by bookie -> 403
  RED-7  : PATCH /api/settings invalid HH:MM -> 422
  RED-8  : PATCH /api/settings start >= end -> 422
  RED-9  : GET /api/blackouts any active user -> 200 []
  RED-10 : POST /api/blackouts admin -> 201
  RED-11 : POST /api/blackouts bookie -> 403
  RED-12 : POST /api/blackouts start_date > end_date -> 422
  RED-13 : DELETE /api/blackouts/{id} admin -> 204
  RED-14 : DELETE /api/blackouts/{id} bookie -> 403
  RED-15 : GET /api/blackouts?farmhouse_id= filters: global + specific, excludes other
  RED-16 : min_advance_notice_minutes=0 (default) -> near-future hold allowed (201)
  RED-17 : min_advance_notice_minutes=120 -> hold 30 min out -> 422
  RED-18 : min_advance_notice_minutes=120 -> hold 3h out -> 201
  RED-19 : global blackout covering booking date -> hold 422
  RED-20 : blackout for different farmhouse -> hold 201 (not blocked)
  RED-21 : operating hours 09:00-23:00 -> single-day 07:00-08:00 local -> 422
  RED-22 : operating hours 09:00-23:00 -> single-day 10:00-12:00 local -> 201
  RED-23 : operating hours set -> multi-day booking -> 201 (no enforcement)
  RED-24 : hold expires_at ~1h when DB hold_duration_hours=1
  RED-25 : future-only still enforced (past start_at -> 422)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

TZ = ZoneInfo("Asia/Karachi")

# A fixed future base date for rule tests (far enough from "now" to avoid
# near-future conflicts). June 15, 2030 is a Saturday (Karachi calendar).
BASE_YEAR, BASE_MONTH, BASE_DAY = 2030, 6, 15


# ---------------------------------------------------------------------------
# Helpers
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
    """Create one admin + one bookie; return (at_admin, at_bookie), (admin_id, bookie_id)."""
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    admin  = User(email="admin@rules-test.com", name="Admin",  password_hash=hash_password("pass"), role="admin",  is_active=True)
    bookie = User(email="bk@rules-test.com",    name="Bookie", password_hash=hash_password("pass"), role="bookie", is_active=True)
    db.add_all([admin, bookie])
    db.commit()
    db.refresh(admin); db.refresh(bookie)
    at_admin  = create_access_token(user_id=admin.id,  role="admin")
    at_bookie = create_access_token(user_id=bookie.id, role="bookie")
    ids = (admin.id, bookie.id)
    db.close()
    return (f"Bearer {at_admin}", f"Bearer {at_bookie}"), ids


def _seed_farmhouse(session_factory, *, operating_hours: str | None = None) -> int:
    from app.models.farmhouse import Farmhouse
    db = session_factory()
    fh = Farmhouse(name="Test FH", buffer_minutes=0, operating_hours=operating_hours, status="active")
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fid = fh.id
    db.close()
    return fid


def _set_settings(session_factory, **kwargs) -> None:
    """Directly set SystemSettings fields in the DB for a given test client."""
    from app.models.settings import get_or_create_settings
    db = session_factory()
    s = get_or_create_settings(db)
    for k, v in kwargs.items():
        setattr(s, k, v)
    db.commit()
    db.close()


def _create_blackout(session_factory, *, farmhouse_id=None, start_date, end_date, reason=None) -> int:
    from app.models.blackout import BlackoutDate
    db = session_factory()
    b = BlackoutDate(
        farmhouse_id=farmhouse_id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    bid = b.id
    db.close()
    return bid


def _karachi_dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Return UTC datetime for the given Asia/Karachi local time."""
    local = datetime(year, month, day, hour, minute, tzinfo=TZ)
    return local.astimezone(timezone.utc)


def _hold_payload(farmhouse_id: int, start: datetime, end: datetime) -> dict:
    return {
        "farmhouse_id": farmhouse_id,
        "start_at": start.isoformat(),
        "end_at":   end.isoformat(),
    }


# ---------------------------------------------------------------------------
# RED-1 / RED-2 : get_or_create_settings
# ---------------------------------------------------------------------------

def test_get_or_create_settings_creates_singleton():
    from app.db import Base
    import app.models  # noqa
    from app.models.settings import get_or_create_settings

    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    Sess = sessionmaker(bind=eng)
    db = Sess()

    s = get_or_create_settings(db)
    assert s.id == 1
    assert s.hold_duration_hours == 24
    assert s.min_advance_notice_minutes == 0
    assert s.default_buffer_minutes == 0
    assert s.operating_hours_start is None
    assert s.operating_hours_end is None
    db.close()


def test_get_or_create_settings_idempotent():
    from app.db import Base
    import app.models  # noqa
    from app.models.settings import get_or_create_settings

    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    Sess = sessionmaker(bind=eng)
    db = Sess()

    s1 = get_or_create_settings(db)
    s2 = get_or_create_settings(db)
    assert s1.id == s2.id == 1
    db.close()


# ---------------------------------------------------------------------------
# RED-3 / RED-4 : GET /api/settings
# ---------------------------------------------------------------------------

def test_get_settings_returns_defaults():
    c = _make_client()
    (at_admin, at_bookie), _ = _seed_users(c._db_session)

    r = c.get("/api/settings", headers={"Authorization": at_bookie})
    assert r.status_code == 200
    body = r.json()
    assert body["hold_duration_hours"] == 24
    assert body["min_advance_notice_minutes"] == 0


def test_get_settings_unauthenticated_401():
    c = _make_client()
    r = c.get("/api/settings")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# RED-5 / RED-6 : PATCH /api/settings
# ---------------------------------------------------------------------------

def test_patch_settings_admin_updates():
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)

    r = c.patch(
        "/api/settings",
        json={"hold_duration_hours": 48, "min_advance_notice_minutes": 60},
        headers={"Authorization": at_admin},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["hold_duration_hours"] == 48
    assert body["min_advance_notice_minutes"] == 60

    # Verify persisted
    r2 = c.get("/api/settings", headers={"Authorization": at_admin})
    assert r2.json()["hold_duration_hours"] == 48


def test_patch_settings_bookie_403():
    c = _make_client()
    (_, at_bookie), _ = _seed_users(c._db_session)

    r = c.patch(
        "/api/settings",
        json={"hold_duration_hours": 1},
        headers={"Authorization": at_bookie},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# RED-7 / RED-8 : PATCH /api/settings validation
# ---------------------------------------------------------------------------

def test_patch_settings_invalid_hhMM():
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)

    r = c.patch(
        "/api/settings",
        json={"operating_hours_start": "9:00"},   # missing leading zero
        headers={"Authorization": at_admin},
    )
    assert r.status_code == 422


def test_patch_settings_start_gte_end():
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)

    r = c.patch(
        "/api/settings",
        json={"operating_hours_start": "23:00", "operating_hours_end": "09:00"},
        headers={"Authorization": at_admin},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# RED-9 / RED-10 / RED-11 / RED-12 : Blackout CRUD
# ---------------------------------------------------------------------------

def test_list_blackouts_any_user():
    c = _make_client()
    (_, at_bookie), _ = _seed_users(c._db_session)

    r = c.get("/api/blackouts", headers={"Authorization": at_bookie})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_blackout_admin_201():
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)

    r = c.post(
        "/api/blackouts",
        json={"start_date": "2030-12-25", "end_date": "2030-12-25", "reason": "Christmas"},
        headers={"Authorization": at_admin},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["start_date"] == "2030-12-25"
    assert body["end_date"]   == "2030-12-25"
    assert body["reason"]     == "Christmas"
    assert body["farmhouse_id"] is None   # global


def test_create_blackout_bookie_403():
    c = _make_client()
    (_, at_bookie), _ = _seed_users(c._db_session)

    r = c.post(
        "/api/blackouts",
        json={"start_date": "2030-12-25", "end_date": "2030-12-25"},
        headers={"Authorization": at_bookie},
    )
    assert r.status_code == 403


def test_create_blackout_start_after_end_422():
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)

    r = c.post(
        "/api/blackouts",
        json={"start_date": "2030-12-26", "end_date": "2030-12-25"},
        headers={"Authorization": at_admin},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# RED-13 / RED-14 : DELETE /api/blackouts/{id}
# ---------------------------------------------------------------------------

def test_delete_blackout_admin_204():
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)

    r = c.post(
        "/api/blackouts",
        json={"start_date": "2030-11-01", "end_date": "2030-11-01"},
        headers={"Authorization": at_admin},
    )
    bid = r.json()["id"]

    r2 = c.delete(f"/api/blackouts/{bid}", headers={"Authorization": at_admin})
    assert r2.status_code == 204


def test_delete_blackout_bookie_403():
    c = _make_client()
    (at_admin, at_bookie), _ = _seed_users(c._db_session)

    r = c.post(
        "/api/blackouts",
        json={"start_date": "2030-11-02", "end_date": "2030-11-02"},
        headers={"Authorization": at_admin},
    )
    bid = r.json()["id"]

    r2 = c.delete(f"/api/blackouts/{bid}", headers={"Authorization": at_bookie})
    assert r2.status_code == 403


# ---------------------------------------------------------------------------
# RED-15 : GET /api/blackouts?farmhouse_id= filter
# ---------------------------------------------------------------------------

def test_list_blackouts_farmhouse_filter():
    """GET /api/blackouts?farmhouse_id=X returns global + that farmhouse, excludes others."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid  = _seed_farmhouse(c._db_session)
    fid2 = _seed_farmhouse(c._db_session)

    c.post("/api/blackouts",
           json={"start_date": "2030-10-01", "end_date": "2030-10-01", "reason": "global"},
           headers={"Authorization": at_admin})
    c.post("/api/blackouts",
           json={"farmhouse_id": fid, "start_date": "2030-10-02", "end_date": "2030-10-02", "reason": "specific"},
           headers={"Authorization": at_admin})
    c.post("/api/blackouts",
           json={"farmhouse_id": fid2, "start_date": "2030-10-03", "end_date": "2030-10-03", "reason": "other"},
           headers={"Authorization": at_admin})

    r = c.get(f"/api/blackouts?farmhouse_id={fid}", headers={"Authorization": at_admin})
    assert r.status_code == 200
    reasons = {b["reason"] for b in r.json()}
    assert "global"   in reasons
    assert "specific" in reasons
    assert "other"    not in reasons


# ---------------------------------------------------------------------------
# RED-16 : min advance notice OFF -> near-future hold allowed
# ---------------------------------------------------------------------------

def test_min_advance_off_allows_near_future():
    """Default min_advance_notice_minutes=0 (OFF) -> hold starting in 5 min is fine."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)

    start = datetime.now(timezone.utc) + timedelta(minutes=5)
    end   = start + timedelta(hours=2)

    r = c.post("/api/bookings/hold", json=_hold_payload(fid, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# RED-17 / RED-18 : min advance notice ON
# ---------------------------------------------------------------------------

def test_min_advance_120_blocks_30min():
    """min_advance_notice=120 -> hold starting in 30 min -> 422."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)
    _set_settings(c._db_session, min_advance_notice_minutes=120)

    start = datetime.now(timezone.utc) + timedelta(minutes=30)
    end   = start + timedelta(hours=2)

    r = c.post("/api/bookings/hold", json=_hold_payload(fid, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 422
    detail = r.json()["detail"].lower()
    assert "120" in detail or "advance" in detail or "minutes" in detail


def test_min_advance_120_allows_3h():
    """min_advance_notice=120 -> hold starting in 3 hours -> 201."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)
    _set_settings(c._db_session, min_advance_notice_minutes=120)

    start = datetime.now(timezone.utc) + timedelta(hours=3)
    end   = start + timedelta(hours=2)

    r = c.post("/api/bookings/hold", json=_hold_payload(fid, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# RED-19 : global blackout blocks hold
# ---------------------------------------------------------------------------

def test_global_blackout_blocks_hold():
    """Global blackout covering booking date -> 422."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)

    start = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 10, 0)
    end   = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 14, 0)

    _create_blackout(
        c._db_session,
        start_date=date(BASE_YEAR, BASE_MONTH, BASE_DAY),
        end_date=date(BASE_YEAR, BASE_MONTH, BASE_DAY),
        reason="Test Holiday",
    )

    r = c.post("/api/bookings/hold", json=_hold_payload(fid, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 422
    detail = r.json()["detail"].lower()
    assert "blackout" in detail or "holiday" in detail or "test holiday" in detail


# ---------------------------------------------------------------------------
# RED-20 : blackout for different farmhouse does NOT block
# ---------------------------------------------------------------------------

def test_different_farmhouse_blackout_does_not_block():
    """Blackout assigned to fid2 does NOT block fid1."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid1 = _seed_farmhouse(c._db_session)
    fid2 = _seed_farmhouse(c._db_session)

    start = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 10, 0)
    end   = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 14, 0)

    _create_blackout(
        c._db_session,
        farmhouse_id=fid2,
        start_date=date(BASE_YEAR, BASE_MONTH, BASE_DAY),
        end_date=date(BASE_YEAR, BASE_MONTH, BASE_DAY),
    )

    r = c.post("/api/bookings/hold", json=_hold_payload(fid1, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# RED-21 / RED-22 : operating hours enforcement (single-day)
# ---------------------------------------------------------------------------

def test_operating_hours_blocks_outside_window():
    """Operating hours 09:00-23:00; single-day 07:00-08:00 local -> 422."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)
    _set_settings(c._db_session, operating_hours_start="09:00", operating_hours_end="23:00")

    start = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 7, 0)
    end   = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 8, 0)

    r = c.post("/api/bookings/hold", json=_hold_payload(fid, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 422
    detail = r.json()["detail"].lower()
    assert "operating" in detail or "hours" in detail


def test_operating_hours_allows_in_window():
    """Operating hours 09:00-23:00; single-day 10:00-12:00 local -> 201."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)
    _set_settings(c._db_session, operating_hours_start="09:00", operating_hours_end="23:00")

    start = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 10, 0)
    end   = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 12, 0)

    r = c.post("/api/bookings/hold", json=_hold_payload(fid, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# RED-23 : operating hours -> multi-day booking -> skip enforcement
# ---------------------------------------------------------------------------

def test_operating_hours_multi_day_skips_enforcement():
    """Multi-day booking with operating hours set -> 201 (no enforcement)."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)
    _set_settings(c._db_session, operating_hours_start="09:00", operating_hours_end="23:00")

    # Start June 15 07:00 local, end June 16 08:00 local — spans two calendar days
    start = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY,     7, 0)
    end   = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY + 1, 8, 0)

    r = c.post("/api/bookings/hold", json=_hold_payload(fid, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# RED-24 : hold expires_at from DB hold_duration_hours
# ---------------------------------------------------------------------------

def test_hold_duration_from_db_settings():
    """expires_at is derived from DB hold_duration_hours=1 -> ~1h ahead."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)
    _set_settings(c._db_session, hold_duration_hours=1)

    start = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 10, 0)
    end   = _karachi_dt(BASE_YEAR, BASE_MONTH, BASE_DAY, 14, 0)

    before = datetime.now(timezone.utc)
    r = c.post("/api/bookings/hold", json=_hold_payload(fid, start, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 201

    expires_at = datetime.fromisoformat(r.json()["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    expected = before + timedelta(hours=1)
    # Allow 30s clock skew
    assert abs((expires_at - expected).total_seconds()) < 30


# ---------------------------------------------------------------------------
# RED-25 : future-only still enforced
# ---------------------------------------------------------------------------

def test_future_only_still_enforced():
    """Past start_at -> 422 even with all business rules at defaults."""
    c = _make_client()
    (at_admin, _), _ = _seed_users(c._db_session)
    fid = _seed_farmhouse(c._db_session)

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    end  = past + timedelta(hours=2)

    r = c.post("/api/bookings/hold", json=_hold_payload(fid, past, end),
               headers={"Authorization": at_admin})
    assert r.status_code == 422
