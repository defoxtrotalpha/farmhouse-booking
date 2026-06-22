"""Cancellation & withdraw — slice #26 (GitHub #26).

TDD order:
  CAN-1  : POST /cancel by non-admin -> 403
  CAN-2  : POST /cancel missing booking -> 404
  CAN-3  : admin cancel a pending -> 200, status=canceled, cancel_reason set, decided_by set
  CAN-4  : admin cancel a booked -> 200, status=canceled
  CAN-5  : admin cancel a hold -> 409 (only pending/booked via /cancel)
  CAN-6  : admin cancel already canceled -> 409

  WD-1   : bookie withdraw own hold -> 200, status=canceled
  WD-2   : bookie withdraw own pending -> 200, status=canceled
  WD-3   : bookie withdraw someone else's hold -> 403
  WD-4   : bookie withdraw own booked via /withdraw -> 409 (must use request-cancel)
  WD-5   : admin withdraw (any bookie's) hold -> 200 (admin can act as bookie)
  WD-6   : missing booking /withdraw -> 404

  RC-1   : bookie request-cancel own booked -> 200, status stays booked, cancel_requested_at set
  RC-2   : request-cancel someone else's booked -> 403
  RC-3   : request-cancel a non-booked (hold) -> 409
  RC-4   : double request-cancel -> 409 (already requested)
  RC-5   : missing booking /request-cancel -> 404

  CC-1   : admin confirm-cancel a requested booked -> 200, status=canceled, decided_by set
  CC-2   : confirm-cancel by non-admin -> 403
  CC-3   : confirm-cancel without a pending request (cancel_requested_at is None) -> 409
  CC-4   : confirm-cancel if status != booked -> 409
  CC-5   : missing booking /confirm-cancel -> 404

  FLOW-1 : cancel a booked frees the slot — a new approval on the same range succeeds
  ACT-1  : activity log 'booking.canceled' emitted by /cancel
  ACT-2  : activity log 'booking.withdrawn' emitted by /withdraw
  ACT-3  : activity log 'booking.cancel_requested' emitted by /request-cancel
  ACT-4  : activity log 'booking.cancel_confirmed' emitted by /confirm-cancel
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as test_conflict_resolution.py)
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
    admin   = User(email="admin@can-test.com",  name="Admin",   password_hash=hash_password("pass"), role="admin",  is_active=True)
    bookie1 = User(email="bk1@can-test.com",    name="Bookie1", password_hash=hash_password("pass"), role="bookie", is_active=True)
    bookie2 = User(email="bk2@can-test.com",    name="Bookie2", password_hash=hash_password("pass"), role="bookie", is_active=True)
    db.add_all([admin, bookie1, bookie2])
    db.commit()
    db.refresh(admin); db.refresh(bookie1); db.refresh(bookie2)

    at_admin = f"Bearer {create_access_token(user_id=admin.id,   role='admin')}"
    at_bk1   = f"Bearer {create_access_token(user_id=bookie1.id, role='bookie')}"
    at_bk2   = f"Bearer {create_access_token(user_id=bookie2.id, role='bookie')}"
    ids = (admin.id, bookie1.id, bookie2.id)
    db.close()
    return (at_admin, at_bk1, at_bk2), ids


def _seed_farmhouse(session_factory) -> int:
    from app.models.farmhouse import Farmhouse

    db = session_factory()
    fh = Farmhouse(name="Cancel Test FH", status="active", buffer_minutes=0)
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fid = fh.id
    db.close()
    return fid


def _insert_booking(session_factory, *, farmhouse_id, bookie_id, status,
                    start_at, end_at, buffer_minutes=0,
                    client_name="Test", client_contact="0300-0000000"):
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
    db.expunge_all()
    db.close()
    return b


def _get_activity_actions(session_factory, booking_id):
    from app.models.activity import ActivityLog

    db = session_factory()
    rows = db.query(ActivityLog).filter(
        ActivityLog.target_type == "booking",
        ActivityLog.target_id == booking_id,
    ).all()
    actions = [r.action for r in rows]
    db.close()
    return actions


def _future(hours: float = 25) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def can_client():
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


# ===========================================================================
# /cancel  (admin only)
# ===========================================================================

class TestAdminCancel:

    # CAN-1: non-admin gets 403
    def test_non_admin_gets_403(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="pending",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/cancel",
            json={"reason": "test"},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 403

    # CAN-2: missing booking -> 404
    def test_missing_booking_404(self, can_client):
        r = can_client.post(
            "/api/bookings/99999/cancel",
            json={"reason": "gone"},
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 404

    # CAN-3: admin cancel a pending -> canceled, cancel_reason, decided_by set
    def test_cancel_pending(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="pending",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/cancel",
            json={"reason": "admin reason"},
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "canceled"
        assert data["cancel_reason"] == "admin reason"
        assert data["decided_by"] == can_client._admin_id
        assert data["decided_at"] is not None

    # CAN-4: admin cancel a booked -> canceled
    def test_cancel_booked(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/cancel",
            json={"reason": "admin cancel booked"},
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "canceled"

    # CAN-5: admin cancel a hold -> 409
    def test_cancel_hold_is_409(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="hold",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/cancel",
            json={"reason": "oops"},
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 409

    # CAN-6: already canceled -> 409
    def test_cancel_already_canceled_is_409(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="canceled",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/cancel",
            json={"reason": "double"},
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 409


# ===========================================================================
# /withdraw  (owner bookie OR admin)
# ===========================================================================

class TestWithdraw:

    # WD-1: bookie withdraw own hold -> canceled
    def test_bookie_withdraw_own_hold(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="hold",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/withdraw",
            json={},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "canceled"

    # WD-2: bookie withdraw own pending -> canceled
    def test_bookie_withdraw_own_pending(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="pending",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/withdraw",
            json={},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "canceled"

    # WD-3: bookie withdraw someone else's hold -> 403
    def test_bookie_withdraw_other_bookie_hold_is_403(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="hold",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/withdraw",
            json={},
            headers={"Authorization": can_client._bookie2_token},
        )
        assert r.status_code == 403

    # WD-4: bookie withdraw own booked via /withdraw -> 409
    def test_bookie_withdraw_booked_is_409(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/withdraw",
            json={},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 409

    # WD-5: admin can withdraw any bookie's hold
    def test_admin_withdraw_any_hold(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="hold",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/withdraw",
            json={},
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "canceled"

    # WD-6: missing booking -> 404
    def test_withdraw_missing_404(self, can_client):
        r = can_client.post(
            "/api/bookings/99999/withdraw",
            json={},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 404


# ===========================================================================
# /request-cancel  (owner bookie OR admin)
# ===========================================================================

class TestRequestCancel:

    # RC-1: bookie request-cancel own booked -> stays booked, cancel_requested_at set
    def test_request_cancel_own_booked(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/request-cancel",
            json={"reason": "need to cancel"},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "booked"  # stays booked
        assert data["cancel_requested_at"] is not None
        assert data["cancel_reason"] == "need to cancel"

    # RC-2: request-cancel someone else's booked -> 403
    def test_request_cancel_other_bookie_is_403(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/request-cancel",
            json={"reason": "unauthorized"},
            headers={"Authorization": can_client._bookie2_token},
        )
        assert r.status_code == 403

    # RC-3: request-cancel a non-booked (hold) -> 409
    def test_request_cancel_hold_is_409(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="hold",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/request-cancel",
            json={"reason": "wrong status"},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 409

    # RC-4: double request-cancel -> 409
    def test_double_request_cancel_is_409(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        # first request succeeds
        r1 = can_client.post(
            f"/api/bookings/{bid}/request-cancel",
            json={"reason": "first"},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r1.status_code == 200
        # second request -> 409
        r2 = can_client.post(
            f"/api/bookings/{bid}/request-cancel",
            json={"reason": "second"},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r2.status_code == 409

    # RC-5: missing booking -> 404
    def test_request_cancel_missing_404(self, can_client):
        r = can_client.post(
            "/api/bookings/99999/request-cancel",
            json={"reason": "gone"},
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 404


# ===========================================================================
# /confirm-cancel  (admin only)
# ===========================================================================

class TestConfirmCancel:

    # CC-1: admin confirm-cancel a requested booked -> canceled
    def test_confirm_cancel_requested_booked(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        # bookie requests cancel
        can_client.post(
            f"/api/bookings/{bid}/request-cancel",
            json={"reason": "please cancel"},
            headers={"Authorization": can_client._bookie1_token},
        )
        # admin confirms
        r = can_client.post(
            f"/api/bookings/{bid}/confirm-cancel",
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "canceled"
        assert data["decided_by"] == can_client._admin_id

    # CC-2: confirm-cancel by non-admin -> 403
    def test_confirm_cancel_non_admin_403(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/confirm-cancel",
            headers={"Authorization": can_client._bookie1_token},
        )
        assert r.status_code == 403

    # CC-3: confirm-cancel without a pending request -> 409
    def test_confirm_cancel_no_request_409(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/confirm-cancel",
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 409

    # CC-4: confirm-cancel if status != booked -> 409
    def test_confirm_cancel_non_booked_409(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="pending",
            start_at=_future(10), end_at=_future(12),
        )
        r = can_client.post(
            f"/api/bookings/{bid}/confirm-cancel",
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 409

    # CC-5: missing booking -> 404
    def test_confirm_cancel_missing_404(self, can_client):
        r = can_client.post(
            "/api/bookings/99999/confirm-cancel",
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 404


# ===========================================================================
# FLOW-1: canceling a booked frees the slot
# ===========================================================================

class TestCancelFreesSlot:

    def test_cancel_booked_frees_slot_for_new_approval(self, can_client):
        """
        1. Insert booking A (bookie1) in 'booked' on fh.
        2. Insert booking B (bookie2) in 'pending' for the same range.
        3. Attempting to approve B fails with 409 (A occupies the slot).
        4. Admin cancels A.
        5. Approve B now succeeds -> 200, status='booked'.
        """
        sf = can_client._db_session
        fh_id = can_client._fh_id
        s = _future(10)
        e = _future(12)

        # Insert A as 'booked', B as 'pending'
        a_id = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=can_client._bookie1_id,
                                status="booked", start_at=s, end_at=e)
        b_id = _insert_booking(sf, farmhouse_id=fh_id, bookie_id=can_client._bookie2_id,
                                status="pending", start_at=s, end_at=e)

        # Step 3: approve B should fail
        r = can_client.post(
            f"/api/bookings/{b_id}/approve",
            headers={"Authorization": can_client._admin_token},
        )
        assert r.status_code == 409

        # Step 4: admin cancels A
        r2 = can_client.post(
            f"/api/bookings/{a_id}/cancel",
            json={"reason": "freeing slot"},
            headers={"Authorization": can_client._admin_token},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "canceled"

        # Step 5: approve B now succeeds
        r3 = can_client.post(
            f"/api/bookings/{b_id}/approve",
            headers={"Authorization": can_client._admin_token},
        )
        assert r3.status_code == 200
        assert r3.json()["status"] == "booked"


# ===========================================================================
# Activity log strings
# ===========================================================================

class TestActivityLogs:

    # ACT-1: /cancel emits 'booking.canceled'
    def test_cancel_emits_booking_canceled(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="pending",
            start_at=_future(10), end_at=_future(12),
        )
        can_client.post(
            f"/api/bookings/{bid}/cancel",
            json={"reason": "log test"},
            headers={"Authorization": can_client._admin_token},
        )
        actions = _get_activity_actions(can_client._db_session, bid)
        assert "booking.canceled" in actions

    # ACT-2: /withdraw emits 'booking.withdrawn'
    def test_withdraw_emits_booking_withdrawn(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="hold",
            start_at=_future(10), end_at=_future(12),
        )
        can_client.post(
            f"/api/bookings/{bid}/withdraw",
            json={},
            headers={"Authorization": can_client._bookie1_token},
        )
        actions = _get_activity_actions(can_client._db_session, bid)
        assert "booking.withdrawn" in actions

    # ACT-3: /request-cancel emits 'booking.cancel_requested'
    def test_request_cancel_emits_action(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        can_client.post(
            f"/api/bookings/{bid}/request-cancel",
            json={"reason": "please"},
            headers={"Authorization": can_client._bookie1_token},
        )
        actions = _get_activity_actions(can_client._db_session, bid)
        assert "booking.cancel_requested" in actions

    # ACT-4: /confirm-cancel emits 'booking.cancel_confirmed'
    def test_confirm_cancel_emits_action(self, can_client):
        bid = _insert_booking(
            can_client._db_session,
            farmhouse_id=can_client._fh_id,
            bookie_id=can_client._bookie1_id,
            status="booked",
            start_at=_future(10), end_at=_future(12),
        )
        can_client.post(
            f"/api/bookings/{bid}/request-cancel",
            json={"reason": "please"},
            headers={"Authorization": can_client._bookie1_token},
        )
        can_client.post(
            f"/api/bookings/{bid}/confirm-cancel",
            headers={"Authorization": can_client._admin_token},
        )
        actions = _get_activity_actions(can_client._db_session, bid)
        assert "booking.cancel_confirmed" in actions
