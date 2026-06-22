"""Availability endpoint — TDD vertical slice.

TDD order executed:
  RED-1 : ranges_intersect overlapping -> GREEN: create app/services/availability.py
  RED-2 : ranges_intersect adjacent (half-open false) -> GREEN immediately
  RED-3 : ranges_intersect disjoint -> GREEN immediately
  RED-4 : ranges_intersect multi-day span -> GREEN immediately
  RED-5 : GET availability 401 unauthenticated -> GREEN: create Booking model + router
  RED-6 : GET availability 404 farmhouse not found -> GREEN immediately
  RED-7 : GET availability 422 start == end -> GREEN immediately
  RED-8 : GET availability 422 start > end -> GREEN immediately
  RED-9 : GET availability returns occupied (hold/pending/booked) intersecting window
  RED-10: GET availability excludes rejected/canceled/expired
  RED-11: GET availability excludes bookings outside the window (half-open boundary)
  RED-12: GET availability multi-day booking returned for window touching any part
  RED-13: GET availability response shape {id, status, start_at, end_at, bookie_id}
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_client():
    """Fresh TestClient with isolated in-memory SQLite."""
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa — registers ALL models including Booking

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
    """Create one bookie; return (bookie_id, bearer_token)."""
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    bookie = User(
        email="bk@avail-test.com",
        name="Bookie",
        password_hash=hash_password("pass"),
        role="bookie",
        is_active=True,
    )
    db.add(bookie)
    db.commit()
    db.refresh(bookie)
    at = create_access_token(user_id=bookie.id, role="bookie")
    bookie_id = bookie.id
    db.close()
    return bookie_id, f"Bearer {at}"


def _seed_farmhouse(session_factory) -> int:
    from app.models.farmhouse import Farmhouse

    db = session_factory()
    fh = Farmhouse(name="Availability Test FH", status="active")
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fh_id = fh.id
    db.close()
    return fh_id


def _insert_booking(session_factory, *, farmhouse_id, bookie_id, status, start_at, end_at) -> int:
    from app.models.booking import Booking

    db = session_factory()
    b = Booking(
        farmhouse_id=farmhouse_id,
        bookie_id=bookie_id,
        status=status,
        start_at=start_at,
        end_at=end_at,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    bid = b.id
    db.close()
    return bid


@pytest.fixture()
def avail_client():
    c = _make_client()
    c._bookie_id, c._bookie_token = _seed_users(c._db_session)  # type: ignore[attr-defined]
    c._farmhouse_id = _seed_farmhouse(c._db_session)             # type: ignore[attr-defined]
    return c


# ---------------------------------------------------------------------------
# RED-1..4 — Pure unit tests: ranges_intersect
# ---------------------------------------------------------------------------

def test_ranges_intersect_overlapping():
    """Two intervals that clearly overlap must return True."""
    from app.services.availability import ranges_intersect

    a_start = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
    a_end   = datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc)
    b_start = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    b_end   = datetime(2026, 6, 22, 16, 0, tzinfo=timezone.utc)

    assert ranges_intersect(a_start, a_end, b_start, b_end) is True


def test_ranges_intersect_adjacent_is_false():
    """Half-open semantics: [a_start, a_end) touching [b_start, b_end) at a_end == b_start
    means they are ADJACENT, not overlapping."""
    from app.services.availability import ranges_intersect

    a_start = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
    a_end   = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    b_start = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    b_end   = datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc)

    assert ranges_intersect(a_start, a_end, b_start, b_end) is False


def test_ranges_intersect_disjoint_is_false():
    from app.services.availability import ranges_intersect

    a_start = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
    a_end   = datetime(2026, 6, 22, 11, 0, tzinfo=timezone.utc)
    b_start = datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc)
    b_end   = datetime(2026, 6, 22, 16, 0, tzinfo=timezone.utc)

    assert ranges_intersect(a_start, a_end, b_start, b_end) is False


def test_ranges_intersect_multiday_span_is_true():
    """Multi-day booking [Mon 10 am, Wed 15:00) intersects window [Tue 00:00, Tue 23:00)."""
    from app.services.availability import ranges_intersect

    mon_10am = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
    wed_3pm  = datetime(2026, 6, 24, 15, 0, tzinfo=timezone.utc)
    tue_0am  = datetime(2026, 6, 23,  0, 0, tzinfo=timezone.utc)
    tue_11pm = datetime(2026, 6, 23, 23, 0, tzinfo=timezone.utc)

    assert ranges_intersect(mon_10am, wed_3pm, tue_0am, tue_11pm) is True


def test_ranges_intersect_a_contains_b():
    """Interval A fully contains B -> intersect."""
    from app.services.availability import ranges_intersect

    a_start = datetime(2026, 6, 22,  8, 0, tzinfo=timezone.utc)
    a_end   = datetime(2026, 6, 22, 20, 0, tzinfo=timezone.utc)
    b_start = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
    b_end   = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)

    assert ranges_intersect(a_start, a_end, b_start, b_end) is True


# ---------------------------------------------------------------------------
# RED-5 — 401 unauthenticated
# ---------------------------------------------------------------------------

def test_availability_requires_auth(avail_client):
    resp = avail_client.get(
        f"/api/farmhouses/{avail_client._farmhouse_id}/availability",
        params={"start": "2026-06-22T00:00:00Z", "end": "2026-06-23T00:00:00Z"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# RED-6 — 404 farmhouse not found
# ---------------------------------------------------------------------------

def test_availability_farmhouse_not_found(avail_client):
    resp = avail_client.get(
        "/api/farmhouses/9999/availability",
        params={"start": "2026-06-22T00:00:00Z", "end": "2026-06-23T00:00:00Z"},
        headers={"Authorization": avail_client._bookie_token},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RED-7/8 — 422 start >= end
# ---------------------------------------------------------------------------

def test_availability_start_equals_end_422(avail_client):
    resp = avail_client.get(
        f"/api/farmhouses/{avail_client._farmhouse_id}/availability",
        params={"start": "2026-06-22T10:00:00Z", "end": "2026-06-22T10:00:00Z"},
        headers={"Authorization": avail_client._bookie_token},
    )
    assert resp.status_code == 422


def test_availability_start_after_end_422(avail_client):
    resp = avail_client.get(
        f"/api/farmhouses/{avail_client._farmhouse_id}/availability",
        params={"start": "2026-06-23T00:00:00Z", "end": "2026-06-22T00:00:00Z"},
        headers={"Authorization": avail_client._bookie_token},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# RED-9 — returns hold/pending/booked entries that intersect the window
# ---------------------------------------------------------------------------

def test_availability_returns_occupied_entries(avail_client):
    fh_id = avail_client._farmhouse_id
    bk_id = avail_client._bookie_id

    b1 = _insert_booking(
        avail_client._db_session,
        farmhouse_id=fh_id, bookie_id=bk_id, status="booked",
        start_at=datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc),
        end_at=  datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc),
    )
    b2 = _insert_booking(
        avail_client._db_session,
        farmhouse_id=fh_id, bookie_id=bk_id, status="hold",
        start_at=datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc),
        end_at=  datetime(2026, 6, 22, 16, 0, tzinfo=timezone.utc),
    )
    b3 = _insert_booking(
        avail_client._db_session,
        farmhouse_id=fh_id, bookie_id=bk_id, status="pending",
        start_at=datetime(2026, 6, 22, 18, 0, tzinfo=timezone.utc),
        end_at=  datetime(2026, 6, 22, 20, 0, tzinfo=timezone.utc),
    )

    resp = avail_client.get(
        f"/api/farmhouses/{fh_id}/availability",
        params={"start": "2026-06-22T00:00:00Z", "end": "2026-06-23T00:00:00Z"},
        headers={"Authorization": avail_client._bookie_token},
    )
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert {b1, b2, b3}.issubset(ids)


# ---------------------------------------------------------------------------
# RED-10 — excludes rejected / canceled / expired
# ---------------------------------------------------------------------------

def test_availability_excludes_non_occupied_statuses(avail_client):
    fh_id = avail_client._farmhouse_id
    bk_id = avail_client._bookie_id

    for st in ("rejected", "canceled", "expired"):
        _insert_booking(
            avail_client._db_session,
            farmhouse_id=fh_id, bookie_id=bk_id, status=st,
            start_at=datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc),
            end_at=  datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc),
        )

    resp = avail_client.get(
        f"/api/farmhouses/{fh_id}/availability",
        params={"start": "2026-06-22T00:00:00Z", "end": "2026-06-23T00:00:00Z"},
        headers={"Authorization": avail_client._bookie_token},
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# RED-11 — half-open boundary: bookings touching the window edge are excluded
# ---------------------------------------------------------------------------

def test_availability_half_open_boundary_excluded(avail_client):
    """Booking ending exactly at window start, or starting exactly at window end,
    must NOT appear (half-open interval semantics)."""
    fh_id = avail_client._farmhouse_id
    bk_id = avail_client._bookie_id

    # booking ends at window_start (half-open: end == window_start -> not overlapping)
    _insert_booking(
        avail_client._db_session,
        farmhouse_id=fh_id, bookie_id=bk_id, status="booked",
        start_at=datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc),
        end_at=  datetime(2026, 6, 22,  0, 0, tzinfo=timezone.utc),  # == window_start
    )
    # booking starts at window_end (half-open: start == window_end -> not overlapping)
    _insert_booking(
        avail_client._db_session,
        farmhouse_id=fh_id, bookie_id=bk_id, status="booked",
        start_at=datetime(2026, 6, 23,  0, 0, tzinfo=timezone.utc),  # == window_end
        end_at=  datetime(2026, 6, 23,  6, 0, tzinfo=timezone.utc),
    )

    resp = avail_client.get(
        f"/api/farmhouses/{fh_id}/availability",
        params={"start": "2026-06-22T00:00:00Z", "end": "2026-06-23T00:00:00Z"},
        headers={"Authorization": avail_client._bookie_token},
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# RED-12 — multi-day booking returned for window touching any part
# ---------------------------------------------------------------------------

def test_availability_multiday_booking_returned_for_touching_window(avail_client):
    """A booking spanning Mon–Wed must appear when querying a Tuesday-only window."""
    fh_id = avail_client._farmhouse_id
    bk_id = avail_client._bookie_id

    bid = _insert_booking(
        avail_client._db_session,
        farmhouse_id=fh_id, bookie_id=bk_id, status="booked",
        start_at=datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc),  # Monday
        end_at=  datetime(2026, 6, 24, 15, 0, tzinfo=timezone.utc),  # Wednesday
    )

    # Query window = Tuesday only
    resp = avail_client.get(
        f"/api/farmhouses/{fh_id}/availability",
        params={"start": "2026-06-23T08:00:00Z", "end": "2026-06-23T20:00:00Z"},
        headers={"Authorization": avail_client._bookie_token},
    )
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert bid in ids


# ---------------------------------------------------------------------------
# RED-13 — response shape: {id, status, start_at, end_at, bookie_id}
# ---------------------------------------------------------------------------

def test_availability_response_shape(avail_client):
    fh_id = avail_client._farmhouse_id
    bk_id = avail_client._bookie_id

    _insert_booking(
        avail_client._db_session,
        farmhouse_id=fh_id, bookie_id=bk_id, status="booked",
        start_at=datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc),
        end_at=  datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc),
    )

    resp = avail_client.get(
        f"/api/farmhouses/{fh_id}/availability",
        params={"start": "2026-06-22T00:00:00Z", "end": "2026-06-23T00:00:00Z"},
        headers={"Authorization": avail_client._bookie_token},
    )
    assert resp.status_code == 200
    entry = resp.json()[0]
    assert set(entry.keys()) >= {"id", "status", "start_at", "end_at", "bookie_id"}
    assert entry["status"] == "booked"
    assert entry["bookie_id"] == bk_id
