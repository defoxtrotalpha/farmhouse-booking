"""Hold a slot → submit Pending — TDD vertical slice (#22).

TDD order:
  RED-1  : POST /api/bookings/hold unauthenticated -> 401
  RED-2  : POST /api/bookings/hold success -> 201 BookingRead, status='hold',
            expires_at ~24h ahead, buffer_minutes_snapshot copied from farmhouse
  RED-3  : hold with start_at in the past -> 422
  RED-4  : hold with start_at >= end_at -> 422
  RED-5  : hold on disabled farmhouse -> 400
  RED-6  : hold on nonexistent farmhouse -> 404
  RED-7  : buffer_minutes_snapshot is copied from farmhouse (non-zero case)
  RED-8  : TWO overlapping holds by different bookies BOTH succeed (soft/competitive)
  RED-9  : POST /api/bookings/{id}/submit transitions hold->pending,
            sets client details, clears expires_at
  RED-10 : submit by non-owner non-admin -> 403
  RED-11 : submit when status != 'hold' -> 409
  RED-12 : GET /api/bookings bookie sees only own; admin sees all
  RED-13 : GET /api/bookings ?status= filter works
  RED-14 : GET /api/bookings/{id} owner can see own booking -> 200
  RED-15 : GET /api/bookings/{id} non-owner bookie -> 403
  RED-16 : GET /api/bookings/{id} nonexistent -> 404
  RED-17 : hold.created activity log entry emitted on hold
  RED-18 : request.submitted activity log entry emitted on submit
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared helpers
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
    """Create one admin + two bookies.

    Returns:
        ((admin_token, bk1_token, bk2_token), (admin_id, bk1_id, bk2_id))
    """
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    admin   = User(email="admin@hold-test.com",  name="Admin",   password_hash=hash_password("pass"), role="admin",  is_active=True)
    bookie1 = User(email="bk1@hold-test.com",    name="Bookie1", password_hash=hash_password("pass"), role="bookie", is_active=True)
    bookie2 = User(email="bk2@hold-test.com",    name="Bookie2", password_hash=hash_password("pass"), role="bookie", is_active=True)
    db.add_all([admin, bookie1, bookie2])
    db.commit()
    db.refresh(admin); db.refresh(bookie1); db.refresh(bookie2)

    at_admin = create_access_token(user_id=admin.id,   role="admin")
    at_bk1   = create_access_token(user_id=bookie1.id, role="bookie")
    at_bk2   = create_access_token(user_id=bookie2.id, role="bookie")

    ids = (admin.id, bookie1.id, bookie2.id)
    db.close()
    return (
        (f"Bearer {at_admin}", f"Bearer {at_bk1}", f"Bearer {at_bk2}"),
        ids,
    )


def _seed_farmhouse(session_factory, *, status: str = "active", buffer_minutes: int = 0) -> int:
    from app.models.farmhouse import Farmhouse

    db = session_factory()
    fh = Farmhouse(name="Hold Test FH", status=status, buffer_minutes=buffer_minutes)
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fh_id = fh.id
    db.close()
    return fh_id


def _future(hours: float = 25) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _hold_body(fh_id: int, *, start_offset_h: float = 25, duration_h: float = 2) -> dict:
    start = _future(start_offset_h)
    end   = start + timedelta(hours=duration_h)
    return {
        "farmhouse_id": fh_id,
        "start_at": start.isoformat(),
        "end_at":   end.isoformat(),
    }


@pytest.fixture()
def hold_client():
    c = _make_client()
    (admin_tok, bk1_tok, bk2_tok), (admin_id, bk1_id, bk2_id) = _seed_users(c._db_session)
    c._admin_token   = admin_tok    # type: ignore[attr-defined]
    c._bookie1_token = bk1_tok      # type: ignore[attr-defined]
    c._bookie2_token = bk2_tok      # type: ignore[attr-defined]
    c._admin_id      = admin_id     # type: ignore[attr-defined]
    c._bookie1_id    = bk1_id       # type: ignore[attr-defined]
    c._bookie2_id    = bk2_id       # type: ignore[attr-defined]
    c._fh_id = _seed_farmhouse(c._db_session)  # type: ignore[attr-defined]
    return c


# ---------------------------------------------------------------------------
# RED-1: unauthenticated hold -> 401
# ---------------------------------------------------------------------------

def test_hold_unauthenticated():
    c = _make_client()
    fh_id = _seed_farmhouse(c._db_session)
    res = c.post("/api/bookings/hold", json=_hold_body(fh_id))
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# RED-2: hold success -> 201, status='hold', expires_at ~24h, buffer=0
# ---------------------------------------------------------------------------

def test_hold_success(hold_client):
    c = hold_client
    before = datetime.now(timezone.utc)
    res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"]                  == "hold"
    assert data["farmhouse_id"]            == c._fh_id
    assert data["bookie_id"]               == c._bookie1_id
    assert data["buffer_minutes_snapshot"] == 0
    assert data["expires_at"] is not None
    # expires_at should be ~24 h from now
    exp = datetime.fromisoformat(data["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    diff = (exp - before).total_seconds()
    assert 23 * 3600 < diff < 25 * 3600, f"expires_at diff {diff:.0f}s is not ~24 h"


# ---------------------------------------------------------------------------
# RED-3: hold with start_at in the past -> 422
# ---------------------------------------------------------------------------

def test_hold_past_start():
    c = _make_client()
    (_, at_bk1, _), _ = _seed_users(c._db_session)
    fh_id = _seed_farmhouse(c._db_session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    body = {
        "farmhouse_id": fh_id,
        "start_at": past.isoformat(),
        "end_at":   (past + timedelta(hours=2)).isoformat(),
    }
    res = c.post("/api/bookings/hold", json=body, headers={"Authorization": at_bk1})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# RED-4: hold with start_at >= end_at -> 422
# ---------------------------------------------------------------------------

def test_hold_start_not_before_end():
    c = _make_client()
    (_, at_bk1, _), _ = _seed_users(c._db_session)
    fh_id = _seed_farmhouse(c._db_session)
    future = _future(25)
    body = {
        "farmhouse_id": fh_id,
        "start_at": future.isoformat(),
        "end_at":   future.isoformat(),  # start == end
    }
    res = c.post("/api/bookings/hold", json=body, headers={"Authorization": at_bk1})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# RED-5: hold on disabled farmhouse -> 400
# ---------------------------------------------------------------------------

def test_hold_disabled_farmhouse():
    c = _make_client()
    (_, at_bk1, _), _ = _seed_users(c._db_session)
    fh_id = _seed_farmhouse(c._db_session, status="disabled")
    res = c.post("/api/bookings/hold", json=_hold_body(fh_id), headers={"Authorization": at_bk1})
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# RED-6: hold on nonexistent farmhouse -> 404
# ---------------------------------------------------------------------------

def test_hold_nonexistent_farmhouse():
    c = _make_client()
    (_, at_bk1, _), _ = _seed_users(c._db_session)
    res = c.post("/api/bookings/hold", json=_hold_body(9999), headers={"Authorization": at_bk1})
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# RED-7: buffer_minutes_snapshot is copied from farmhouse (non-zero)
# ---------------------------------------------------------------------------

def test_hold_buffer_snapshot_copied():
    c = _make_client()
    (_, at_bk1, _), _ = _seed_users(c._db_session)
    fh_id = _seed_farmhouse(c._db_session, buffer_minutes=30)
    res = c.post("/api/bookings/hold", json=_hold_body(fh_id), headers={"Authorization": at_bk1})
    assert res.status_code == 201
    assert res.json()["buffer_minutes_snapshot"] == 30


# ---------------------------------------------------------------------------
# RED-8: two overlapping holds by different bookies -> both 201 (soft/competitive)
# ---------------------------------------------------------------------------

def test_overlapping_holds_both_succeed(hold_client):
    c = hold_client
    body = _hold_body(c._fh_id)  # identical slot
    res1 = c.post("/api/bookings/hold", json=body, headers={"Authorization": c._bookie1_token})
    res2 = c.post("/api/bookings/hold", json=body, headers={"Authorization": c._bookie2_token})
    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["id"] != res2.json()["id"]
    assert res1.json()["status"] == "hold"
    assert res2.json()["status"] == "hold"


# ---------------------------------------------------------------------------
# RED-9: submit transitions hold->pending, sets details, clears expires_at
# ---------------------------------------------------------------------------

def test_submit_hold_to_pending(hold_client):
    c = hold_client
    hold_res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    assert hold_res.status_code == 201
    booking_id = hold_res.json()["id"]

    submit_body = {
        "client_name":    "Alice Smith",
        "client_contact": "+92300000000",
        "event_type":     "Wedding",
        "event_info":     "300 guests",
        "notes":          "Need outdoor setup",
        "quoted_price":   150000.0,
    }
    res = c.post(
        f"/api/bookings/{booking_id}/submit",
        json=submit_body,
        headers={"Authorization": c._bookie1_token},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"]         == "pending"
    assert data["client_name"]    == "Alice Smith"
    assert data["client_contact"] == "+92300000000"
    assert data["event_type"]     == "Wedding"
    assert data["event_info"]     == "300 guests"
    assert data["notes"]          == "Need outdoor setup"
    assert data["quoted_price"]   == 150000.0
    assert data["expires_at"]     is None  # cleared on submit


# ---------------------------------------------------------------------------
# RED-10: submit by non-owner non-admin -> 403
# ---------------------------------------------------------------------------

def test_submit_by_non_owner_forbidden(hold_client):
    c = hold_client
    hold_res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    booking_id = hold_res.json()["id"]

    res = c.post(
        f"/api/bookings/{booking_id}/submit",
        json={"client_name": "X", "client_contact": "Y"},
        headers={"Authorization": c._bookie2_token},  # different bookie, not admin
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# RED-11: submit when status != 'hold' -> 409
# ---------------------------------------------------------------------------

def test_submit_when_not_hold(hold_client):
    c = hold_client
    hold_res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    booking_id = hold_res.json()["id"]
    # First submit -> now 'pending'
    c.post(
        f"/api/bookings/{booking_id}/submit",
        json={"client_name": "X", "client_contact": "Y"},
        headers={"Authorization": c._bookie1_token},
    )
    # Second submit -> 409 (not a hold anymore)
    res = c.post(
        f"/api/bookings/{booking_id}/submit",
        json={"client_name": "X", "client_contact": "Y"},
        headers={"Authorization": c._bookie1_token},
    )
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# RED-12: GET /api/bookings role filtering
# ---------------------------------------------------------------------------

def test_list_bookings_role_filter(hold_client):
    c = hold_client
    # bookie1 creates a hold
    c.post("/api/bookings/hold", json=_hold_body(c._fh_id),       headers={"Authorization": c._bookie1_token})
    # bookie2 creates a hold at a different time slot
    c.post("/api/bookings/hold", json=_hold_body(c._fh_id, start_offset_h=30),
           headers={"Authorization": c._bookie2_token})

    # Bookie1 sees only own bookings
    res_bk1 = c.get("/api/bookings", headers={"Authorization": c._bookie1_token})
    assert res_bk1.status_code == 200
    bk1_bookings = res_bk1.json()
    assert len(bk1_bookings) >= 1
    assert all(b["bookie_id"] == c._bookie1_id for b in bk1_bookings)

    # Admin sees all
    res_admin = c.get("/api/bookings", headers={"Authorization": c._admin_token})
    assert res_admin.status_code == 200
    assert len(res_admin.json()) >= 2


# ---------------------------------------------------------------------------
# RED-13: GET /api/bookings ?status= filter
# ---------------------------------------------------------------------------

def test_list_bookings_status_filter(hold_client):
    c = hold_client
    hold_res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    booking_id = hold_res.json()["id"]
    # Submit it -> now pending
    c.post(
        f"/api/bookings/{booking_id}/submit",
        json={"client_name": "A", "client_contact": "B"},
        headers={"Authorization": c._bookie1_token},
    )
    # Filter pending -> must include it
    res = c.get("/api/bookings?status=pending", headers={"Authorization": c._bookie1_token})
    assert res.status_code == 200
    assert any(b["id"] == booking_id for b in res.json())
    # Filter hold -> must NOT include it (it's now pending)
    res2 = c.get("/api/bookings?status=hold", headers={"Authorization": c._bookie1_token})
    assert all(b["id"] != booking_id for b in res2.json())


# ---------------------------------------------------------------------------
# RED-14: GET /api/bookings/{id} owner can see own booking -> 200
# ---------------------------------------------------------------------------

def test_get_booking_by_owner(hold_client):
    c = hold_client
    hold_res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    booking_id = hold_res.json()["id"]
    res = c.get(f"/api/bookings/{booking_id}", headers={"Authorization": c._bookie1_token})
    assert res.status_code == 200
    assert res.json()["id"] == booking_id


# ---------------------------------------------------------------------------
# RED-15: GET /api/bookings/{id} non-owner bookie -> 403
# ---------------------------------------------------------------------------

def test_get_booking_non_owner_forbidden(hold_client):
    c = hold_client
    hold_res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    booking_id = hold_res.json()["id"]
    res = c.get(f"/api/bookings/{booking_id}", headers={"Authorization": c._bookie2_token})
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# RED-16: GET /api/bookings/{id} nonexistent -> 404
# ---------------------------------------------------------------------------

def test_get_booking_not_found(hold_client):
    c = hold_client
    res = c.get("/api/bookings/9999", headers={"Authorization": c._bookie1_token})
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# RED-17: hold.created activity log entry emitted
# ---------------------------------------------------------------------------

def test_hold_creates_activity_log(hold_client):
    c = hold_client
    hold_res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    assert hold_res.status_code == 201
    booking_id = hold_res.json()["id"]

    from app.models.activity import ActivityLog

    db = c._db_session()
    try:
        logs = (
            db.query(ActivityLog)
            .filter(
                ActivityLog.action      == "hold.created",
                ActivityLog.target_type == "booking",
                ActivityLog.target_id   == booking_id,
            )
            .all()
        )
    finally:
        db.close()

    assert len(logs) == 1
    assert logs[0].actor_id == c._bookie1_id


# ---------------------------------------------------------------------------
# RED-18: request.submitted activity log entry emitted
# ---------------------------------------------------------------------------

def test_submit_creates_activity_log(hold_client):
    c = hold_client
    hold_res = c.post(
        "/api/bookings/hold",
        json=_hold_body(c._fh_id),
        headers={"Authorization": c._bookie1_token},
    )
    booking_id = hold_res.json()["id"]
    c.post(
        f"/api/bookings/{booking_id}/submit",
        json={"client_name": "A", "client_contact": "B"},
        headers={"Authorization": c._bookie1_token},
    )

    from app.models.activity import ActivityLog

    db = c._db_session()
    try:
        logs = (
            db.query(ActivityLog)
            .filter(
                ActivityLog.action      == "request.submitted",
                ActivityLog.target_type == "booking",
                ActivityLog.target_id   == booking_id,
            )
            .all()
        )
    finally:
        db.close()

    assert len(logs) == 1
    assert logs[0].actor_id == c._bookie1_id
