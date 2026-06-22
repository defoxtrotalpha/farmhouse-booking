"""Approve booking -> booked (+ overlap exclusion) — TDD vertical slice (#23).

TDD order:
  RED-1 : find_booked_conflict - overlapping booked booking -> returns it
  RED-2 : find_booked_conflict - disjoint booking -> None
  RED-3 : find_booked_conflict - pending/hold overlapping -> None (not counted)
  RED-4 : find_booked_conflict - different farmhouse -> None
  RED-5 : find_booked_conflict - buffer gap causes conflict (within-buffer)
  RED-6 : find_booked_conflict - exclude_booking_id excludes self
  RED-7 : POST /api/bookings/{id}/approve pending -> 200 booked, decided_by/decided_at set
  RED-8 : POST /api/bookings/{id}/approve non-pending (hold) -> 409
  RED-9 : POST /api/bookings/{id}/approve by non-admin -> 403
  RED-10: POST /api/bookings/{id}/approve missing id -> 404
  RED-11: Two overlapping pendings: approve first -> 200; approve second -> 409 stays pending;
          exactly one is booked
  RED-12: Two non-overlapping pendings on same farmhouse: both approve -> both booked
  RED-13: 'booking.approved' activity entry emitted on success
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared DB / client helpers (mirror test_booking_hold.py pattern)
# ---------------------------------------------------------------------------

def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _make_client(eng=None):
    """Fresh TestClient backed by an isolated in-memory SQLite DB."""
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa — registers ALL models with Base.metadata

    if eng is None:
        eng = _make_engine()
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
    """Create one admin + two bookies."""
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    admin   = User(email="admin@approve-test.com",  name="Admin",   password_hash=hash_password("pass"), role="admin",  is_active=True)
    bookie1 = User(email="bk1@approve-test.com",    name="Bookie1", password_hash=hash_password("pass"), role="bookie", is_active=True)
    bookie2 = User(email="bk2@approve-test.com",    name="Bookie2", password_hash=hash_password("pass"), role="bookie", is_active=True)
    db.add_all([admin, bookie1, bookie2])
    db.commit()
    db.refresh(admin); db.refresh(bookie1); db.refresh(bookie2)

    at_admin = f"Bearer {create_access_token(user_id=admin.id,   role='admin')}"
    at_bk1   = f"Bearer {create_access_token(user_id=bookie1.id, role='bookie')}"
    at_bk2   = f"Bearer {create_access_token(user_id=bookie2.id, role='bookie')}"
    ids = (admin.id, bookie1.id, bookie2.id)
    db.close()
    return (at_admin, at_bk1, at_bk2), ids


def _seed_farmhouse(session_factory, *, status: str = "active", buffer_minutes: int = 0) -> int:
    from app.models.farmhouse import Farmhouse

    db = session_factory()
    fh = Farmhouse(name="Approve Test FH", status=status, buffer_minutes=buffer_minutes)
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fh_id = fh.id
    db.close()
    return fh_id


def _future(hours: float = 25) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _insert_booking(session_factory, *, farmhouse_id, bookie_id, status,
                    start_at, end_at, buffer_minutes=0,
                    client_name="Test Client", client_contact="0300-0000000"):
    """Insert a booking row directly into the DB and return its id."""
    from app.models.booking import Booking

    db = session_factory()
    b = Booking(
        farmhouse_id=farmhouse_id,
        bookie_id=bookie_id,
        status=status,
        start_at=start_at,
        end_at=end_at,
        buffer_minutes_snapshot=buffer_minutes,
        client_name=client_name,
        client_contact=client_contact,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    bid = b.id
    db.close()
    return bid


def _get_booking(session_factory, booking_id):
    from app.models.booking import Booking

    db = session_factory()
    b = db.get(Booking, booking_id)
    data = {
        "id": b.id,
        "status": b.status,
        "decided_by": b.decided_by,
        "decided_at": b.decided_at,
    }
    db.close()
    return data


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def approve_client():
    c = _make_client()
    (at_admin, at_bk1, at_bk2), (admin_id, bk1_id, bk2_id) = _seed_users(c._db_session)
    c._admin_token   = at_admin
    c._bookie1_token = at_bk1
    c._bookie2_token = at_bk2
    c._admin_id      = admin_id
    c._bookie1_id    = bk1_id
    c._bookie2_id    = bk2_id
    c._fh_id = _seed_farmhouse(c._db_session)
    return c


@pytest.fixture()
def approve_client_30buf():
    """Client whose default farmhouse has buffer_minutes=30."""
    c = _make_client()
    (at_admin, at_bk1, at_bk2), (admin_id, bk1_id, bk2_id) = _seed_users(c._db_session)
    c._admin_token   = at_admin
    c._bookie1_token = at_bk1
    c._bookie2_token = at_bk2
    c._admin_id      = admin_id
    c._bookie1_id    = bk1_id
    c._bookie2_id    = bk2_id
    c._fh_id = _seed_farmhouse(c._db_session, buffer_minutes=30)
    return c


# ===========================================================================
# ─── UNIT TESTS for find_booked_conflict ────────────────────────────────────
# ===========================================================================

class TestFindBookedConflict:
    """Direct unit tests for the find_booked_conflict helper."""

    def _setup(self):
        """Returns (session_factory, admin_id, bk1_id, fh_id) for a fresh isolated DB."""
        eng = _make_engine()
        from app.db import Base
        import app.models  # noqa
        Base.metadata.create_all(eng)
        sf = sessionmaker(bind=eng, autoflush=False, autocommit=False)
        (_, _, _), (admin_id, bk1_id, _) = _seed_users(sf)
        fh_id = _seed_farmhouse(sf, buffer_minutes=0)
        return sf, admin_id, bk1_id, fh_id

    # RED-1: overlapping booked booking -> returns it
    def test_conflict_found_when_booked_overlaps(self):
        from app.services.booking_engine import find_booked_conflict

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        # Existing booked: T to T+2h
        bid = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                              status="booked",
                              start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        result = find_booked_conflict(db, farmhouse_id=fh_id,
                                      start_at=T + timedelta(hours=1),
                                      end_at=T + timedelta(hours=3),
                                      buffer_minutes=0)
        db.close()
        assert result is not None
        assert result.id == bid

    # RED-2: disjoint booking -> None
    def test_no_conflict_disjoint(self):
        from app.services.booking_engine import find_booked_conflict

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                        status="booked",
                        start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        # Proposed slot is AFTER the booked one (no buffer -> no overlap)
        result = find_booked_conflict(db, farmhouse_id=fh_id,
                                      start_at=T + timedelta(hours=3),
                                      end_at=T + timedelta(hours=5),
                                      buffer_minutes=0)
        db.close()
        assert result is None

    # RED-3: pending/hold overlapping -> None (soft/competitive)
    def test_pending_and_hold_not_counted(self):
        from app.services.booking_engine import find_booked_conflict

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        for s in ("pending", "hold"):
            _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                            status=s,
                            start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        result = find_booked_conflict(db, farmhouse_id=fh_id,
                                      start_at=T, end_at=T + timedelta(hours=2),
                                      buffer_minutes=0)
        db.close()
        assert result is None

    # RED-4: different farmhouse -> None
    def test_different_farmhouse_no_conflict(self):
        from app.services.booking_engine import find_booked_conflict

        sf, _, bk1_id, fh_id = self._setup()
        fh_other = _seed_farmhouse(sf, buffer_minutes=0)
        T = _future(10)
        _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                        status="booked",
                        start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        # Check against different farmhouse
        result = find_booked_conflict(db, farmhouse_id=fh_other,
                                      start_at=T, end_at=T + timedelta(hours=2),
                                      buffer_minutes=0)
        db.close()
        assert result is None

    # RED-5: buffer gap causes conflict (within-buffer adjacency)
    def test_buffer_padding_causes_conflict(self):
        """Buffer=30 min; A booked 10:00-12:00; B proposed 12:15-14:00.
        A occupies [09:30, 12:30); B occupies [11:45, 14:30) -> conflict."""
        from app.services.booking_engine import find_booked_conflict

        sf, _, bk1_id, fh_id = self._setup()
        base = _future(10)
        # Normalize to a clean hour boundary for clarity
        T = base.replace(minute=0, second=0, microsecond=0)

        # Booking A: booked T to T+2h, buffer=30
        a_id = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                               status="booked", buffer_minutes=30,
                               start_at=T, end_at=T + timedelta(hours=2))

        db = sf()
        # Proposed B: T+2h15min to T+4h, buffer=30
        # B buffered: [T+1h45min, T+4h30min), A buffered [T-30min, T+2h30min)
        # Intersection: 1h45m < 2h30m AND -30m < 4h30m -> YES
        result = find_booked_conflict(db, farmhouse_id=fh_id,
                                      start_at=T + timedelta(hours=2, minutes=15),
                                      end_at=T + timedelta(hours=4),
                                      buffer_minutes=30)
        db.close()
        assert result is not None, "Expected conflict due to buffer padding"
        assert result.id == a_id

    # RED-5b: booking outside buffer -> no conflict
    def test_buffer_padding_no_conflict_outside_buffer(self):
        """Buffer=30 min; A booked T to T+2h; C proposed T+3h to T+5h.
        A occupies [T-30, T+2h30); C occupies [T+2h30, T+5h30) -> touching, NOT conflicting."""
        from app.services.booking_engine import find_booked_conflict

        sf, _, bk1_id, fh_id = self._setup()
        base = _future(10)
        T = base.replace(minute=0, second=0, microsecond=0)

        _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                        status="booked", buffer_minutes=30,
                        start_at=T, end_at=T + timedelta(hours=2))

        db = sf()
        # C starts exactly at T+3h (buffer-end of A is T+2h30min; C-buffer-start is T+2h30min)
        # T+2h30 < T+2h30 is FALSE -> no intersection
        result = find_booked_conflict(db, farmhouse_id=fh_id,
                                      start_at=T + timedelta(hours=3),
                                      end_at=T + timedelta(hours=5),
                                      buffer_minutes=30)
        db.close()
        assert result is None, "T+3h start with 30m buffer should NOT conflict with T-T+2h booked"

    # RED-6: exclude_booking_id excludes self
    def test_exclude_booking_id_skips_self(self):
        from app.services.booking_engine import find_booked_conflict

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        bid = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                              status="booked",
                              start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        # Without exclude -> finds itself
        result = find_booked_conflict(db, farmhouse_id=fh_id,
                                      start_at=T, end_at=T + timedelta(hours=2),
                                      buffer_minutes=0,
                                      exclude_booking_id=None)
        assert result is not None and result.id == bid

        # With exclude -> no conflict
        result2 = find_booked_conflict(db, farmhouse_id=fh_id,
                                       start_at=T, end_at=T + timedelta(hours=2),
                                       buffer_minutes=0,
                                       exclude_booking_id=bid)
        db.close()
        assert result2 is None


# ===========================================================================
# ─── HTTP endpoint tests ─────────────────────────────────────────────────────
# ===========================================================================

# RED-7: approve pending -> 200 booked, decided_by/decided_at set
def test_approve_pending_becomes_booked(approve_client):
    c = approve_client
    T = _future()
    bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                          bookie_id=c._bookie1_id, status="pending",
                          start_at=T, end_at=T + timedelta(hours=2))

    before = datetime.now(timezone.utc)
    res = c.post(f"/api/bookings/{bid}/approve",
                 headers={"Authorization": c._admin_token})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "booked"
    assert data["decided_by"] == c._admin_id

    decided_at = datetime.fromisoformat(data["decided_at"])
    if decided_at.tzinfo is None:
        decided_at = decided_at.replace(tzinfo=timezone.utc)
    assert decided_at >= before, "decided_at should be >= time before approve call"


# RED-8: approve non-pending (hold) -> 409
def test_approve_hold_returns_409(approve_client):
    c = approve_client
    T = _future()
    bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                          bookie_id=c._bookie1_id, status="hold",
                          start_at=T, end_at=T + timedelta(hours=2))
    res = c.post(f"/api/bookings/{bid}/approve",
                 headers={"Authorization": c._admin_token})
    assert res.status_code == 409
    assert "pending" in res.json()["detail"].lower()


# RED-9: approve by non-admin -> 403
def test_approve_by_non_admin_returns_403(approve_client):
    c = approve_client
    T = _future()
    bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                          bookie_id=c._bookie1_id, status="pending",
                          start_at=T, end_at=T + timedelta(hours=2))
    res = c.post(f"/api/bookings/{bid}/approve",
                 headers={"Authorization": c._bookie1_token})
    assert res.status_code == 403


# RED-10: approve missing id -> 404
def test_approve_missing_id_returns_404(approve_client):
    c = approve_client
    res = c.post("/api/bookings/99999/approve",
                 headers={"Authorization": c._admin_token})
    assert res.status_code == 404


# RED-11: Two overlapping pendings -> first approve succeeds; second -> 409 stays pending
def test_two_overlapping_pendings_only_first_approved(approve_client_30buf):
    c = approve_client_30buf
    T = _future()
    T = T.replace(minute=0, second=0, microsecond=0)

    # Both occupy same buffered range (overlap with buffer)
    bid1 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                           bookie_id=c._bookie1_id, status="pending",
                           start_at=T, end_at=T + timedelta(hours=2),
                           buffer_minutes=30)
    bid2 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                           bookie_id=c._bookie2_id, status="pending",
                           start_at=T + timedelta(minutes=30),
                           end_at=T + timedelta(hours=2, minutes=30),
                           buffer_minutes=30)

    # Approve first -> 200
    res1 = c.post(f"/api/bookings/{bid1}/approve",
                  headers={"Authorization": c._admin_token})
    assert res1.status_code == 200, res1.text
    assert res1.json()["status"] == "booked"

    # Approve second -> 409 conflict
    res2 = c.post(f"/api/bookings/{bid2}/approve",
                  headers={"Authorization": c._admin_token})
    assert res2.status_code == 409
    body2 = res2.json()
    assert "conflict" in body2["detail"].lower()
    assert body2["conflict_booking_id"] == bid1

    # Second booking still pending in DB
    b2 = _get_booking(c._db_session, bid2)
    assert b2["status"] == "pending"

    # Exactly one booking is in 'booked' status on this farmhouse
    from app.models.booking import Booking
    db = c._db_session()
    booked_count = db.query(Booking).filter(
        Booking.farmhouse_id == c._fh_id, Booking.status == "booked"
    ).count()
    db.close()
    assert booked_count == 1


# RED-12: Two non-overlapping pendings on same farmhouse: both can be approved
def test_two_non_overlapping_pendings_both_approved(approve_client):
    c = approve_client
    T = _future()
    T = T.replace(minute=0, second=0, microsecond=0)

    # Slot A: T to T+2h (no buffer)
    bid1 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                           bookie_id=c._bookie1_id, status="pending",
                           start_at=T, end_at=T + timedelta(hours=2),
                           buffer_minutes=0)
    # Slot B: T+3h to T+5h (no buffer, well separated)
    bid2 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                           bookie_id=c._bookie2_id, status="pending",
                           start_at=T + timedelta(hours=3),
                           end_at=T + timedelta(hours=5),
                           buffer_minutes=0)

    res1 = c.post(f"/api/bookings/{bid1}/approve",
                  headers={"Authorization": c._admin_token})
    assert res1.status_code == 200, res1.text

    res2 = c.post(f"/api/bookings/{bid2}/approve",
                  headers={"Authorization": c._admin_token})
    assert res2.status_code == 200, res2.text

    assert res1.json()["status"] == "booked"
    assert res2.json()["status"] == "booked"


# RED-13: 'booking.approved' activity entry emitted on success
def test_approve_emits_activity_log(approve_client):
    c = approve_client
    T = _future()
    bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                          bookie_id=c._bookie1_id, status="pending",
                          start_at=T, end_at=T + timedelta(hours=2))

    res = c.post(f"/api/bookings/{bid}/approve",
                 headers={"Authorization": c._admin_token})
    assert res.status_code == 200, res.text

    from app.models.activity import ActivityLog
    db = c._db_session()
    log = db.query(ActivityLog).filter(
        ActivityLog.action == "booking.approved",
        ActivityLog.target_id == bid,
        ActivityLog.target_type == "booking",
        ActivityLog.actor_id == c._admin_id,
    ).first()
    db.close()
    assert log is not None, "Expected 'booking.approved' activity log entry"
