"""Invite-a-Bookie slice — TDD vertical slice (GitHub #19 / local issue #04).

Tests are added ONE behavior at a time (RED → GREEN).
All DB tests use isolated in-memory SQLite via dependency_overrides.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_client():
    """Fresh TestClient backed by a new in-memory SQLite DB."""
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa — registers all models with Base.metadata

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

    from fastapi.testclient import TestClient
    client = TestClient(application)
    client._db_session = TestSession  # type: ignore[attr-defined]
    return client


def _seed_admin(session_factory):
    """Create an admin user; return (db_id, Bearer token string)."""
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    admin = User(
        email="admin@test.com",
        name="Admin",
        password_hash=hash_password("adminpass"),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    token = create_access_token(user_id=admin.id, role="admin")
    db.close()
    return admin.id, f"Bearer {token}"


def _seed_bookie(session_factory):
    """Create a bookie user; return Bearer token string."""
    from app.models.user import User
    from app.security import hash_password, create_access_token

    db = session_factory()
    bookie = User(
        email="bookie@test.com",
        name="Bookie",
        password_hash=hash_password("bookiepass"),
        role="bookie",
        is_active=True,
    )
    db.add(bookie)
    db.commit()
    db.refresh(bookie)
    token = create_access_token(user_id=bookie.id, role="bookie")
    db.close()
    return f"Bearer {token}"


# ===========================================================================
# Step 1 — InviteToken SQLAlchemy model
# ===========================================================================

def test_invite_token_model_has_expected_fields():
    """InviteToken can be persisted with the required fields."""
    from app.db import Base
    import app.models  # noqa
    from app.models.invite import InviteToken
    from app.models.user import User

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    db = Session()

    user = User(email="b@test.com", name="B", role="bookie", is_active=False)
    db.add(user)
    db.commit()
    db.refresh(user)

    token_str = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=72)
    invite = InviteToken(user_id=user.id, token=token_str, expires_at=expires)
    db.add(invite)
    db.commit()
    db.refresh(invite)

    assert invite.id is not None
    assert invite.token == token_str
    assert invite.used_at is None
    assert invite.expires_at.tzinfo is not None
    assert invite.created_at is not None
    db.close()


# ===========================================================================
# Step 2 — POST /api/invites: admin creates inactive bookie + token + email
# ===========================================================================

@pytest.fixture()
def invite_client():
    client = _make_client()
    _, client._admin_token = _seed_admin(client._db_session)  # type: ignore[attr-defined]
    client._bookie_token = _seed_bookie(client._db_session)  # type: ignore[attr-defined]
    return client


def test_admin_invite_creates_inactive_bookie_user(invite_client, caplog):
    """POST /api/invites: admin → 201, user created with is_active=False, role=bookie."""
    import logging
    with caplog.at_level(logging.INFO, logger="app.email"):
        resp = invite_client.post(
            "/api/invites",
            json={"name": "New Bookie", "email": "newbookie@test.com"},
            headers={"Authorization": invite_client._admin_token},
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["email"] == "newbookie@test.com"
    assert data["name"] == "New Bookie"
    assert data["role"] == "bookie"
    assert "id" in data
    # token must NOT appear in the response
    assert "token" not in data

    # DB: user is inactive, no password set
    from app.models.user import User
    db = invite_client._db_session()
    user = db.query(User).filter_by(email="newbookie@test.com").first()
    assert user is not None
    assert user.is_active is False
    assert user.password_hash is None

    # DB: an invite token exists for this user
    from app.models.invite import InviteToken
    token_row = db.query(InviteToken).filter_by(user_id=user.id).first()
    assert token_row is not None
    assert token_row.used_at is None
    db.close()

    # Email was "sent" (logged) and body contains the set-password URL
    email_logs = [r for r in caplog.records if r.name == "app.email"]
    assert email_logs, "Expected an email log record"
    body_log = email_logs[0].getMessage()
    assert "/set-password?token=" in body_log


# ===========================================================================
# Step 3 — Non-admin invite blocked (403)
# ===========================================================================

def test_bookie_cannot_invite(invite_client):
    resp = invite_client.post(
        "/api/invites",
        json={"name": "X", "email": "x@test.com"},
        headers={"Authorization": invite_client._bookie_token},
    )
    assert resp.status_code == 403


# ===========================================================================
# Step 4 — Duplicate email → 409
# ===========================================================================

def test_duplicate_email_returns_409(invite_client):
    # Invite once successfully
    invite_client.post(
        "/api/invites",
        json={"name": "Dup", "email": "dup@test.com"},
        headers={"Authorization": invite_client._admin_token},
    )
    # Invite again with same email
    resp = invite_client.post(
        "/api/invites",
        json={"name": "Dup2", "email": "dup@test.com"},
        headers={"Authorization": invite_client._admin_token},
    )
    assert resp.status_code == 409


# ===========================================================================
# Step 5 — POST /api/invites/set-password: valid token activates user
# ===========================================================================

def _do_invite(client, email="active@test.com", name="New User"):
    """Helper: invite a user and return the raw token string from DB."""
    resp = client.post(
        "/api/invites",
        json={"name": name, "email": email},
        headers={"Authorization": client._admin_token},
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]
    from app.models.invite import InviteToken
    db = client._db_session()
    token_row = db.query(InviteToken).filter_by(user_id=user_id).first()
    token_str = token_row.token
    db.close()
    return token_str


def test_set_password_valid_token_activates_user(invite_client):
    token_str = _do_invite(invite_client, email="setpw@test.com")

    resp = invite_client.post(
        "/api/invites/set-password",
        json={"token": token_str, "password": "newpassword123"},
    )
    assert resp.status_code == 200, resp.text

    # DB: user is now active and has a password
    from app.models.user import User
    from app.security import verify_password
    db = invite_client._db_session()
    user = db.query(User).filter_by(email="setpw@test.com").first()
    assert user.is_active is True
    assert user.password_hash is not None
    assert verify_password("newpassword123", user.password_hash)

    # Token is consumed (used_at set)
    from app.models.invite import InviteToken
    token_row = db.query(InviteToken).filter_by(token=token_str).first()
    assert token_row.used_at is not None
    db.close()


# ===========================================================================
# Step 6 — Expired token rejected (400)
# ===========================================================================

def test_expired_token_returns_400(invite_client):
    """Manually insert an already-expired invite token and confirm 400."""
    from app.models.user import User
    from app.models.invite import InviteToken

    db = invite_client._db_session()
    # Create an inactive user
    user = User(email="expired@test.com", name="Exp", role="bookie", is_active=False)
    db.add(user)
    db.flush()
    # Token that expired in the past
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token_str = secrets.token_urlsafe(32)
    invite = InviteToken(user_id=user.id, token=token_str, expires_at=past)
    db.add(invite)
    db.commit()
    db.close()

    resp = invite_client.post(
        "/api/invites/set-password",
        json={"token": token_str, "password": "somepassword"},
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


# ===========================================================================
# Step 7 — Reused token rejected on second use (400)
# ===========================================================================

def test_reused_token_returns_400(invite_client):
    token_str = _do_invite(invite_client, email="reuse@test.com")

    # First use — success
    r1 = invite_client.post(
        "/api/invites/set-password",
        json={"token": token_str, "password": "firstpassword"},
    )
    assert r1.status_code == 200

    # Second use — must fail
    r2 = invite_client.post(
        "/api/invites/set-password",
        json={"token": token_str, "password": "anotherpassword"},
    )
    assert r2.status_code == 400
    assert "already been used" in r2.json()["detail"].lower()


# ===========================================================================
# Step 8 — Too-short password rejected (422)
# ===========================================================================

def test_short_password_returns_422(invite_client):
    token_str = _do_invite(invite_client, email="shortpw@test.com")
    resp = invite_client.post(
        "/api/invites/set-password",
        json={"token": token_str, "password": "short"},
    )
    assert resp.status_code == 422


# ===========================================================================
# Step 9 — End-to-end: invite → set-password → login succeeds
# ===========================================================================

def test_full_invite_flow_ends_with_successful_login(invite_client):
    """Invite a bookie → set password → login → /me returns bookie role."""
    # 1. Admin invites
    token_str = _do_invite(invite_client, email="fullflow@test.com", name="Full Flow")

    # 2. Set password
    r_pw = invite_client.post(
        "/api/invites/set-password",
        json={"token": token_str, "password": "strongpassword99"},
    )
    assert r_pw.status_code == 200, r_pw.text

    # 3. Login
    r_login = invite_client.post(
        "/api/auth/login",
        json={"email": "fullflow@test.com", "password": "strongpassword99"},
    )
    assert r_login.status_code == 200, r_login.text
    login_data = r_login.json()
    assert "access_token" in login_data

    # 4. /me confirms bookie role
    r_me = invite_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_data['access_token']}"},
    )
    assert r_me.status_code == 200, r_me.text
    me = r_me.json()
    assert me["email"] == "fullflow@test.com"
    assert me["role"] == "bookie"
