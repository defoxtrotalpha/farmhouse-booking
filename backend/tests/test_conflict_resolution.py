"""Conflict resolution — auto-detect & reject overlapping pendings (slice #24, GitHub #24).

TDD order:
  UNIT-1 : find_overlapping_unresolved — overlapping hold -> returned
  UNIT-2 : find_overlapping_unresolved — overlapping pending -> returned
  UNIT-3 : find_overlapping_unresolved — booked overlapping -> NOT returned
  UNIT-4 : find_overlapping_unresolved — rejected/canceled/expired overlapping -> NOT returned
  UNIT-5 : find_overlapping_unresolved — different farmhouse -> NOT returned
  UNIT-6 : find_overlapping_unresolved — exclude_booking_id excludes self
  UNIT-7 : find_overlapping_unresolved — buffer causes overlap (non-overlapping raw range)
  UNIT-8 : find_overlapping_unresolved — disjoint -> empty list

  API-1  : GET /api/bookings/{id}/conflicts by non-admin -> 403
  API-2  : GET /api/bookings/{id}/conflicts missing id -> 404
  API-3  : GET /api/bookings/{id}/conflicts returns overlapping hold/pending losers
  API-4  : GET /api/bookings/{id}/conflicts excludes itself and non-overlapping

  API-5  : POST /reject by non-admin -> 403
  API-6  : POST /reject missing id -> 404
  API-7  : POST /reject pending -> 200, status=rejected, decided_by/at/reason set
  API-8  : POST /reject hold -> 200, status=rejected
  API-9  : POST /reject booked -> 409
  API-10 : POST /reject already-rejected -> 409
  API-11 : POST /reject empty reason -> 422

  API-12 : POST /reject-batch rejects multiple pendings, skips booked/rejected
  API-13 : POST /reject-batch: booked row stays booked (untouched)
  API-14 : activity log 'request.rejected' emitted for each rejection

  FLOW-1 : approve A -> booked; approve overlapping B -> 409 conflict_id==A.id;
           then reject B -> 200
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared DB / client helpers  (same pattern as test_booking_approve.py)
# ---------------------------------------------------------------------------

def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _make_client(eng=None):
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa

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
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    admin   = User(email="admin@cr-test.com",  name="Admin",   password_hash=hash_password("pass"), role="admin",  is_active=True)
    bookie1 = User(email="bk1@cr-test.com",    name="Bookie1", password_hash=hash_password("pass"), role="bookie", is_active=True)
    bookie2 = User(email="bk2@cr-test.com",    name="Bookie2", password_hash=hash_password("pass"), role="bookie", is_active=True)
    db.add_all([admin, bookie1, bookie2])
    db.commit()
    db.refresh(admin); db.refresh(bookie1); db.refresh(bookie2)

    at_admin = f"Bearer {create_access_token(user_id=admin.id,   role='admin')}"
    at_bk1   = f"Bearer {create_access_token(user_id=bookie1.id, role='bookie')}"
    at_bk2   = f"Bearer {create_access_token(user_id=bookie2.id, role='bookie')}"
    ids = (admin.id, bookie1.id, bookie2.id)
    db.close()
    return (at_admin, at_bk1, at_bk2), ids


def _seed_farmhouse(session_factory, *, buffer_minutes: int = 0) -> int:
    from app.models.farmhouse import Farmhouse

    db = session_factory()
    fh = Farmhouse(name="CR Test FH", status="active", buffer_minutes=buffer_minutes)
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fid = fh.id
    db.close()
    return fid


def _insert_booking(session_factory, *, farmhouse_id, bookie_id, status,
                    start_at, end_at, buffer_minutes=0):
    from app.models.booking import Booking

    db = session_factory()
    b = Booking(
        farmhouse_id=farmhouse_id,
        bookie_id=bookie_id,
        status=status,
        start_at=start_at,
        end_at=end_at,
        buffer_minutes_snapshot=buffer_minutes,
        client_name="Test",
        client_contact="0300-0000000",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    bid = b.id
    db.close()
    return bid


def _get_booking_status(session_factory, booking_id):
    from app.models.booking import Booking

    db = session_factory()
    b = db.get(Booking, booking_id)
    status = b.status if b else None
    db.close()
    return status


def _future(hours: float = 25) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def cr_client():
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
def cr_client_30buf():
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
# UNIT tests — find_overlapping_unresolved
# ===========================================================================

class TestFindOverlappingUnresolved:

    def _setup(self):
        eng = _make_engine()
        from app.db import Base
        import app.models  # noqa
        Base.metadata.create_all(eng)
        sf = sessionmaker(bind=eng, autoflush=False, autocommit=False)
        (_, _, _), (admin_id, bk1_id, _) = _seed_users(sf)
        fh_id = _seed_farmhouse(sf)
        return sf, admin_id, bk1_id, fh_id

    # UNIT-1: overlapping hold is returned
    def test_overlapping_hold_returned(self):
        from app.services.booking_engine import find_overlapping_unresolved

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        bid = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                              status="hold",
                              start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        results = find_overlapping_unresolved(db, farmhouse_id=fh_id,
                                              start_at=T + timedelta(hours=1),
                                              end_at=T + timedelta(hours=3),
                                              buffer_minutes=0)
        db.close()
        assert len(results) == 1
        assert results[0].id == bid

    # UNIT-2: overlapping pending is returned
    def test_overlapping_pending_returned(self):
        from app.services.booking_engine import find_overlapping_unresolved

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        bid = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                              status="pending",
                              start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        results = find_overlapping_unresolved(db, farmhouse_id=fh_id,
                                              start_at=T + timedelta(hours=1),
                                              end_at=T + timedelta(hours=3),
                                              buffer_minutes=0)
        db.close()
        assert len(results) == 1
        assert results[0].id == bid

    # UNIT-3: booked overlapping -> NOT returned (only hold/pending)
    def test_booked_not_returned(self):
        from app.services.booking_engine import find_overlapping_unresolved

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                        status="booked",
                        start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        results = find_overlapping_unresolved(db, farmhouse_id=fh_id,
                                              start_at=T, end_at=T + timedelta(hours=2),
                                              buffer_minutes=0)
        db.close()
        assert results == []

    # UNIT-4: rejected/canceled/expired overlapping -> NOT returned
    def test_terminal_statuses_not_returned(self):
        from app.services.booking_engine import find_overlapping_unresolved

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        for s in ("rejected", "canceled", "expired"):
            _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                            status=s,
                            start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        results = find_overlapping_unresolved(db, farmhouse_id=fh_id,
                                              start_at=T, end_at=T + timedelta(hours=2),
                                              buffer_minutes=0)
        db.close()
        assert results == []

    # UNIT-5: different farmhouse -> NOT returned
    def test_different_farmhouse_not_returned(self):
        from app.services.booking_engine import find_overlapping_unresolved

        sf, _, bk1_id, fh_id = self._setup()
        other_fh_id = _seed_farmhouse(sf)
        T = _future(10)
        _insert_booking(sf, farmhouse_id=other_fh_id, bookie_id=bk1_id,
                        status="hold",
                        start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        results = find_overlapping_unresolved(db, farmhouse_id=fh_id,
                                              start_at=T, end_at=T + timedelta(hours=2),
                                              buffer_minutes=0)
        db.close()
        assert results == []

    # UNIT-6: exclude_booking_id excludes self
    def test_exclude_booking_id(self):
        from app.services.booking_engine import find_overlapping_unresolved

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        bid = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                              status="pending",
                              start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        results = find_overlapping_unresolved(db, farmhouse_id=fh_id,
                                              start_at=T, end_at=T + timedelta(hours=2),
                                              buffer_minutes=0,
                                              exclude_booking_id=bid)
        db.close()
        assert results == []

    # UNIT-7: buffer causes overlap even when raw ranges don't overlap
    def test_buffer_causes_overlap(self):
        from app.services.booking_engine import find_overlapping_unresolved

        sf, _, bk1_id, fh_id = _seed_farmhouse.__wrapped__ if hasattr(_seed_farmhouse, '__wrapped__') else (None, None, None, None)
        # use _setup for a fresh db
        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        # existing: hold T+2h to T+4h  (buffer=30 min -> buffered [T+90min, T+270min))
        bid = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                              status="hold",
                              start_at=T + timedelta(hours=2),
                              end_at=T + timedelta(hours=4),
                              buffer_minutes=30)
        db = sf()
        # proposed: T to T+2h  buffer=30 -> buffered [T-30min, T+150min)
        # candidate buffered [T+90min, T+270min)  -> 90 < 150 AND 90 < 150 -> overlap
        results = find_overlapping_unresolved(db, farmhouse_id=fh_id,
                                              start_at=T,
                                              end_at=T + timedelta(hours=2),
                                              buffer_minutes=30)
        db.close()
        assert len(results) == 1
        assert results[0].id == bid

    # UNIT-8: disjoint ranges -> empty list
    def test_disjoint_returns_empty(self):
        from app.services.booking_engine import find_overlapping_unresolved

        sf, _, bk1_id, fh_id = self._setup()
        T = _future(10)
        _insert_booking(sf, farmhouse_id=fh_id, bookie_id=bk1_id,
                        status="pending",
                        start_at=T, end_at=T + timedelta(hours=2))
        db = sf()
        # proposed range starts 3h after existing ends -> no overlap
        results = find_overlapping_unresolved(db, farmhouse_id=fh_id,
                                              start_at=T + timedelta(hours=5),
                                              end_at=T + timedelta(hours=7),
                                              buffer_minutes=0)
        db.close()
        assert results == []


# ===========================================================================
# API tests — GET /api/bookings/{id}/conflicts
# ===========================================================================

class TestGetConflicts:

    # API-1: non-admin -> 403
    def test_non_admin_forbidden(self, cr_client):
        c = cr_client
        T = _future(10)
        bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                               bookie_id=c._bookie1_id, status="booked",
                               start_at=T, end_at=T + timedelta(hours=2))
        r = c.get(f"/api/bookings/{bid}/conflicts",
                  headers={"Authorization": c._bookie1_token})
        assert r.status_code == 403

    # API-2: missing id -> 404
    def test_missing_booking_404(self, cr_client):
        c = cr_client
        r = c.get("/api/bookings/99999/conflicts",
                  headers={"Authorization": c._admin_token})
        assert r.status_code == 404

    # API-3: returns overlapping hold+pending losers for a booked booking
    def test_returns_overlapping_losers(self, cr_client):
        c = cr_client
        T = _future(10)
        # The "winner" — booked
        booked_id = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                                     bookie_id=c._admin_id, status="booked",
                                     start_at=T, end_at=T + timedelta(hours=4))
        # Loser 1: hold overlapping
        hold_id = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                                   bookie_id=c._bookie1_id, status="hold",
                                   start_at=T + timedelta(hours=1),
                                   end_at=T + timedelta(hours=3))
        # Loser 2: pending overlapping
        pending_id = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                                      bookie_id=c._bookie2_id, status="pending",
                                      start_at=T + timedelta(hours=2),
                                      end_at=T + timedelta(hours=5))
        r = c.get(f"/api/bookings/{booked_id}/conflicts",
                  headers={"Authorization": c._admin_token})
        assert r.status_code == 200
        ids = [b["id"] for b in r.json()]
        assert hold_id in ids
        assert pending_id in ids

    # API-4: excludes itself and non-overlapping bookings
    def test_excludes_self_and_nonoverlapping(self, cr_client):
        c = cr_client
        T = _future(10)
        booked_id = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                                     bookie_id=c._admin_id, status="booked",
                                     start_at=T, end_at=T + timedelta(hours=2))
        # Non-overlapping pending (starts after booked ends)
        non_overlap_id = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                                          bookie_id=c._bookie1_id, status="pending",
                                          start_at=T + timedelta(hours=5),
                                          end_at=T + timedelta(hours=7))
        r = c.get(f"/api/bookings/{booked_id}/conflicts",
                  headers={"Authorization": c._admin_token})
        assert r.status_code == 200
        ids = [b["id"] for b in r.json()]
        assert booked_id not in ids        # excludes itself
        assert non_overlap_id not in ids   # no overlap


# ===========================================================================
# API tests — POST /api/bookings/{id}/reject
# ===========================================================================

class TestRejectBooking:

    # API-5: non-admin -> 403
    def test_non_admin_forbidden(self, cr_client):
        c = cr_client
        T = _future(10)
        bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                               bookie_id=c._bookie1_id, status="pending",
                               start_at=T, end_at=T + timedelta(hours=2))
        r = c.post(f"/api/bookings/{bid}/reject",
                   json={"reason": "sorry"},
                   headers={"Authorization": c._bookie1_token})
        assert r.status_code == 403

    # API-6: missing id -> 404
    def test_missing_booking_404(self, cr_client):
        c = cr_client
        r = c.post("/api/bookings/99999/reject",
                   json={"reason": "sorry"},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 404

    # API-7: pending -> 200, status=rejected, fields set
    def test_reject_pending_success(self, cr_client):
        c = cr_client
        T = _future(10)
        bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                               bookie_id=c._bookie1_id, status="pending",
                               start_at=T, end_at=T + timedelta(hours=2))
        r = c.post(f"/api/bookings/{bid}/reject",
                   json={"reason": "slot taken"},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "rejected"
        assert data["reason"] == "slot taken"
        assert data["decided_by"] == c._admin_id
        assert data["decided_at"] is not None

    # API-8: hold -> 200, status=rejected
    def test_reject_hold_success(self, cr_client):
        c = cr_client
        T = _future(10)
        bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                               bookie_id=c._bookie1_id, status="hold",
                               start_at=T, end_at=T + timedelta(hours=2))
        r = c.post(f"/api/bookings/{bid}/reject",
                   json={"reason": "no capacity"},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    # API-9: booked -> 409 (not rejectable)
    def test_reject_booked_409(self, cr_client):
        c = cr_client
        T = _future(10)
        bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                               bookie_id=c._bookie1_id, status="booked",
                               start_at=T, end_at=T + timedelta(hours=2))
        r = c.post(f"/api/bookings/{bid}/reject",
                   json={"reason": "oops"},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 409

    # API-10: already rejected -> 409
    def test_reject_already_rejected_409(self, cr_client):
        c = cr_client
        T = _future(10)
        bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                               bookie_id=c._bookie1_id, status="rejected",
                               start_at=T, end_at=T + timedelta(hours=2))
        r = c.post(f"/api/bookings/{bid}/reject",
                   json={"reason": "double reject"},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 409

    # API-11: empty reason -> 422
    def test_reject_empty_reason_422(self, cr_client):
        c = cr_client
        T = _future(10)
        bid = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                               bookie_id=c._bookie1_id, status="pending",
                               start_at=T, end_at=T + timedelta(hours=2))
        r = c.post(f"/api/bookings/{bid}/reject",
                   json={"reason": ""},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 422


# ===========================================================================
# API tests — POST /api/bookings/reject-batch
# ===========================================================================

class TestRejectBatch:

    # API-12: rejects multiple pendings, skips non-rejectable
    def test_batch_rejects_pendings(self, cr_client):
        c = cr_client
        T = _future(10)
        p1 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                              bookie_id=c._bookie1_id, status="pending",
                              start_at=T, end_at=T + timedelta(hours=1))
        p2 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                              bookie_id=c._bookie2_id, status="pending",
                              start_at=T + timedelta(hours=1),
                              end_at=T + timedelta(hours=2))
        already_rejected = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                                            bookie_id=c._bookie1_id, status="rejected",
                                            start_at=T + timedelta(hours=3),
                                            end_at=T + timedelta(hours=4))
        r = c.post("/api/bookings/reject-batch",
                   json={"booking_ids": [p1, p2, already_rejected],
                         "reason": "slot taken by winner"},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 200
        data = r.json()
        assert p1 in data["rejected"]
        assert p2 in data["rejected"]
        skipped_ids = [s["id"] for s in data["skipped"]]
        assert already_rejected in skipped_ids

    # API-13: booked row stays booked after batch reject (untouched)
    def test_batch_leaves_booked_untouched(self, cr_client):
        c = cr_client
        T = _future(10)
        booked_id = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                                     bookie_id=c._admin_id, status="booked",
                                     start_at=T, end_at=T + timedelta(hours=2))
        pending_id = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                                      bookie_id=c._bookie1_id, status="pending",
                                      start_at=T, end_at=T + timedelta(hours=2))
        r = c.post("/api/bookings/reject-batch",
                   json={"booking_ids": [booked_id, pending_id],
                         "reason": "loser"},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 200
        data = r.json()
        # booked should be skipped
        skipped_ids = [s["id"] for s in data["skipped"]]
        assert booked_id in skipped_ids
        # pending was rejected
        assert pending_id in data["rejected"]
        # booked row still booked in DB
        assert _get_booking_status(c._db_session, booked_id) == "booked"

    # API-14: activity log 'request.rejected' emitted for each rejection
    def test_activity_log_emitted(self, cr_client):
        from app.models.activity import ActivityLog

        c = cr_client
        T = _future(10)
        p1 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                              bookie_id=c._bookie1_id, status="pending",
                              start_at=T, end_at=T + timedelta(hours=2))
        r = c.post(f"/api/bookings/{p1}/reject",
                   json={"reason": "testing activity"},
                   headers={"Authorization": c._admin_token})
        assert r.status_code == 200

        db = c._db_session()
        log = db.query(ActivityLog).filter(
            ActivityLog.action == "request.rejected",
            ActivityLog.target_id == p1,
        ).first()
        db.close()
        assert log is not None
        assert log.note == "testing activity"
        assert log.actor_id == c._admin_id


# ===========================================================================
# Integration flow — approve A, conflicting approve B fails, then reject B
# ===========================================================================

class TestConflictRejectFlow:

    def test_approve_booked_then_conflicting_approve_then_reject(self, cr_client):
        """
        FLOW-1: approve A (booked), approve overlapping B -> 409 conflict_id==A.id,
                then POST /reject on B succeeds -> B becomes rejected.
        """
        c = cr_client
        T = _future(10)

        # B1 (will be approved first) and B2 (overlapping, will fail approval)
        b1 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                              bookie_id=c._bookie1_id, status="pending",
                              start_at=T, end_at=T + timedelta(hours=3))
        b2 = _insert_booking(c._db_session, farmhouse_id=c._fh_id,
                              bookie_id=c._bookie2_id, status="pending",
                              start_at=T + timedelta(hours=1),
                              end_at=T + timedelta(hours=4))

        # Approve b1 -> booked
        r1 = c.post(f"/api/bookings/{b1}/approve",
                    headers={"Authorization": c._admin_token})
        assert r1.status_code == 200
        assert r1.json()["status"] == "booked"

        # Approve b2 -> 409, conflict_booking_id == b1
        r2 = c.post(f"/api/bookings/{b2}/approve",
                    headers={"Authorization": c._admin_token})
        assert r2.status_code == 409
        data2 = r2.json()
        assert data2["conflict_booking_id"] == b1

        # Reject b2 using the reject endpoint
        r3 = c.post(f"/api/bookings/{b2}/reject",
                    json={"reason": "slot already taken by #{}".format(b1)},
                    headers={"Authorization": c._admin_token})
        assert r3.status_code == 200
        assert r3.json()["status"] == "rejected"

        # b1 still booked
        assert _get_booking_status(c._db_session, b1) == "booked"
