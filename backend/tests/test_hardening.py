"""Hardening & end-to-end smoke tests (#32).

Covers two non-functional acceptance criteria:
  1. Every /api endpoint (outside a small public allowlist) rejects
     unauthenticated requests — verified dynamically across all routes.
  2. A full core-journey smoke test:
        invite -> set-password -> login -> hold -> submit -> approve
        -> notify -> cancel (slot freed).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Isolated app/client factory
# ---------------------------------------------------------------------------

def _make_app_client():
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa — populate Base.metadata

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

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    return app, client, TestSession


# Endpoints that are intentionally public (no auth required).
_PUBLIC = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/signup"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/invites/set-password"),
}


def _fill_path(path: str) -> str:
    """Replace {param} path segments with a dummy value."""
    out = []
    for seg in path.split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            out.append("1")
        else:
            out.append(seg)
    return "/".join(out)


# ---------------------------------------------------------------------------
# 1. Auth-guard sweep: every protected endpoint rejects no-token requests
# ---------------------------------------------------------------------------

def test_all_protected_endpoints_require_auth():
    from fastapi.routing import APIRoute

    app, client, _ = _make_app_client()

    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api"):
            continue
        for method in route.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            if (method, route.path) in _PUBLIC:
                continue
            url = _fill_path(route.path)
            resp = client.request(method, url)  # no Authorization header
            assert resp.status_code in (401, 403), (
                f"{method} {url} returned {resp.status_code}, expected 401/403 "
                f"(endpoint may be missing an auth guard)"
            )
            checked += 1

    assert checked > 10  # sanity: we actually exercised the routes


# ---------------------------------------------------------------------------
# Helpers for the e2e journey
# ---------------------------------------------------------------------------

def _seed_admin(session_factory):
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    admin = User(
        email="admin@e2e.test",
        name="E2E Admin",
        password_hash=hash_password("adminpass"),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    token = create_access_token(user_id=admin.id, role="admin")
    admin_id = admin.id
    db.close()
    return admin_id, f"Bearer {token}"


def _seed_farmhouse(session_factory):
    from app.models.farmhouse import Farmhouse

    db = session_factory()
    fh = Farmhouse(name="E2E Farmhouse", status="active", buffer_minutes=0)
    db.add(fh)
    db.commit()
    db.refresh(fh)
    fh_id = fh.id
    db.close()
    return fh_id


# ---------------------------------------------------------------------------
# 2. End-to-end core journey smoke test
# ---------------------------------------------------------------------------

def test_e2e_core_journey():
    from app.models.invite import InviteToken
    from app.models.notification import Notification
    from app.models.booking import Booking

    app, client, Session = _make_app_client()
    _admin_id, admin_auth = _seed_admin(Session)
    fh_id = _seed_farmhouse(Session)

    # --- invite a bookie (admin) ------------------------------------------
    r = client.post(
        "/api/invites",
        json={"email": "bookie@example.com", "name": "E2E Bookie"},
        headers={"Authorization": admin_auth},
    )
    assert r.status_code == 201

    # token is emailed only — read it from the DB for the test
    db = Session()
    invite = db.query(InviteToken).order_by(InviteToken.id.desc()).first()
    token_str = invite.token
    db.close()

    # --- set password / activate (public) ---------------------------------
    r = client.post("/api/invites/set-password", json={"token": token_str, "password": "bookiepass1"})
    assert r.status_code == 200

    # --- login as bookie ---------------------------------------------------
    r = client.post("/api/auth/login", json={"email": "bookie@example.com", "password": "bookiepass1"})
    assert r.status_code == 200
    bookie_auth = f"Bearer {r.json()['access_token']}"

    # --- place a hold ------------------------------------------------------
    start = datetime.now(timezone.utc) + timedelta(days=3)
    end = start + timedelta(hours=3)
    r = client.post(
        "/api/bookings/hold",
        json={"farmhouse_id": fh_id, "start_at": start.isoformat(), "end_at": end.isoformat()},
        headers={"Authorization": bookie_auth},
    )
    assert r.status_code == 201, r.text
    booking_id = r.json()["id"]

    # --- submit (-> pending) ----------------------------------------------
    r = client.post(
        f"/api/bookings/{booking_id}/submit",
        json={
            "client_name": "Smith Wedding",
            "client_contact": "smith@example.com",
            "event_type": "wedding",
            "event_info": None,
            "notes": None,
            "quoted_price": 1500.0,
        },
        headers={"Authorization": bookie_auth},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    # --- approve (-> booked) ----------------------------------------------
    r = client.post(f"/api/bookings/{booking_id}/approve", headers={"Authorization": admin_auth})
    assert r.status_code == 200
    assert r.json()["status"] == "booked"

    # --- notify: the bookie received a booking.approved notification ------
    db = Session()
    approved_notifs = (
        db.query(Notification)
        .filter(Notification.type == "booking.approved", Notification.booking_id == booking_id)
        .all()
    )
    assert any(n.recipient_id is not None for n in approved_notifs)
    db.close()

    # --- cancel (admin) ----------------------------------------------------
    r = client.post(
        f"/api/bookings/{booking_id}/cancel",
        json={"reason": "Client postponed"},
        headers={"Authorization": admin_auth},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "canceled"

    # --- slot is freed: no 'booked' bookings remain on the farmhouse ------
    db = Session()
    remaining_booked = (
        db.query(Booking)
        .filter(Booking.farmhouse_id == fh_id, Booking.status == "booked")
        .count()
    )
    assert remaining_booked == 0
    db.close()
