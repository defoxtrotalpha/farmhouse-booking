"""Activity Log slice — TDD vertical slice (GitHub #28 / local issue #13).

Behaviors tested ONE at a time (RED -> GREEN):
  1. log_activity() inserts a row with correct fields
  2. GET /api/activity as admin returns all entries newest-first
  3. GET /api/activity as bookie returns only own entries
  4. GET /api/activity unauthenticated -> 401
  5. No PUT/PATCH/DELETE routes exist for activity (append-only)
  6. POST /api/auth/login emits 'user.login' entry
  7. POST /api/invites emits 'bookie.invited' entry
  8. POST /api/invites/set-password emits 'bookie.activated' entry
"""
from __future__ import annotations

import logging
import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Shared helpers  (mirror the pattern from test_invite.py)
# ---------------------------------------------------------------------------

def _make_activity_client():
    """Fresh TestClient backed by a new in-memory SQLite DB."""
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa — registers ALL models (incl. ActivityLog) with Base.metadata

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
    """Create an admin; return (user_id, 'Bearer <token>')."""
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
    user_id = admin.id
    db.close()
    return user_id, f"Bearer {token}"


def _seed_bookie(session_factory):
    """Create a bookie; return (user_id, 'Bearer <token>')."""
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
    user_id = bookie.id
    db.close()
    return user_id, f"Bearer {token}"


@pytest.fixture()
def act_client():
    """TestClient with seeded admin + bookie."""
    client = _make_activity_client()
    admin_id, admin_token = _seed_admin(client._db_session)
    bookie_id, bookie_token = _seed_bookie(client._db_session)
    client._admin_id = admin_id          # type: ignore[attr-defined]
    client._admin_token = admin_token    # type: ignore[attr-defined]
    client._bookie_id = bookie_id        # type: ignore[attr-defined]
    client._bookie_token = bookie_token  # type: ignore[attr-defined]
    return client


# ===========================================================================
# Step 1 — log_activity() inserts a row with correct fields
# ===========================================================================

def test_log_activity_inserts_row_with_correct_fields():
    """log_activity() must create a persisted ActivityLog with all given fields."""
    from app.db import Base
    import app.models  # noqa
    from app.models.activity import ActivityLog
    from app.services.activity import log_activity

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    db = Session()

    entry = log_activity(
        db,
        actor_id=1,
        action="user.login",
        target_type="user",
        target_id=1,
        note="test note",
    )
    db.commit()

    assert entry.id is not None
    assert entry.actor_id == 1
    assert entry.action == "user.login"
    assert entry.target_type == "user"
    assert entry.target_id == 1
    assert entry.note == "test note"
    assert entry.created_at is not None
    assert entry.created_at.tzinfo is not None  # must be timezone-aware

    db.close()
    eng.dispose()


def test_log_activity_works_with_nullable_fields():
    """log_activity() must accept actor_id=None (system action) and nullable optional fields."""
    from app.db import Base
    import app.models  # noqa
    from app.models.activity import ActivityLog
    from app.services.activity import log_activity

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    db = Session()

    entry = log_activity(db, actor_id=None, action="system.startup")
    db.commit()

    assert entry.id is not None
    assert entry.actor_id is None
    assert entry.action == "system.startup"
    assert entry.target_type is None
    assert entry.target_id is None
    assert entry.note is None

    db.close()
    eng.dispose()


# ===========================================================================
# Step 2 — GET /api/activity: admin sees ALL entries, newest first
# ===========================================================================

def test_get_activity_admin_sees_all_entries_newest_first(act_client):
    """Admin GET /api/activity returns all log entries ordered newest-first."""
    from app.models.activity import ActivityLog

    db = act_client._db_session()
    older = ActivityLog(
        actor_id=act_client._bookie_id,
        action="bookie.action",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    newer = ActivityLog(
        actor_id=act_client._admin_id,
        action="admin.action",
        created_at=datetime.now(timezone.utc),
    )
    db.add_all([older, newer])
    db.commit()
    db.close()

    resp = act_client.get("/api/activity", headers={"Authorization": act_client._admin_token})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2

    # Newest first: admin.action must appear before bookie.action
    actions = [e["action"] for e in data]
    assert actions.index("admin.action") < actions.index("bookie.action")

    # Each entry has expected keys
    entry = data[0]
    for key in ("id", "actor_id", "action", "target_type", "target_id", "note", "created_at"):
        assert key in entry, f"Missing key: {key}"


def test_get_activity_admin_pagination(act_client):
    """GET /api/activity supports ?limit= and ?offset= params."""
    from app.models.activity import ActivityLog

    db = act_client._db_session()
    for i in range(5):
        db.add(ActivityLog(actor_id=act_client._admin_id, action=f"action.{i}"))
    db.commit()
    db.close()

    # limit=2 should return exactly 2
    resp = act_client.get("/api/activity?limit=2&offset=0", headers={"Authorization": act_client._admin_token})
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # offset=3 on 5 items should return 2
    resp2 = act_client.get("/api/activity?limit=10&offset=3", headers={"Authorization": act_client._admin_token})
    assert resp2.status_code == 200
    assert len(resp2.json()) == 2


# ===========================================================================
# Step 3 — GET /api/activity: bookie sees ONLY own entries
# ===========================================================================

def test_get_activity_bookie_sees_only_own_entries(act_client):
    """Bookie GET /api/activity sees only entries where actor_id == their own id."""
    from app.models.activity import ActivityLog

    db = act_client._db_session()
    own = ActivityLog(actor_id=act_client._bookie_id, action="bookie.own.action", note="mine")
    other = ActivityLog(actor_id=act_client._admin_id, action="admin.other.action", note="not mine")
    db.add_all([own, other])
    db.commit()
    db.close()

    resp = act_client.get("/api/activity", headers={"Authorization": act_client._bookie_token})
    assert resp.status_code == 200
    data = resp.json()

    actor_ids = {e["actor_id"] for e in data}
    assert actor_ids <= {act_client._bookie_id}, f"Saw entries from other actors: {actor_ids}"
    actions = [e["action"] for e in data]
    assert "admin.other.action" not in actions
    assert "bookie.own.action" in actions


def test_get_activity_bookie_does_not_see_other_bookie_entries(act_client):
    """Bookie cannot see another bookie's entries."""
    from app.models.user import User
    from app.security import hash_password, create_access_token
    from app.models.activity import ActivityLog

    # Create a second bookie
    db = act_client._db_session()
    bookie2 = User(email="bookie2@test.com", name="Bookie2", password_hash=hash_password("pass"), role="bookie", is_active=True)
    db.add(bookie2)
    db.commit()
    db.refresh(bookie2)
    bookie2_id = bookie2.id
    db.add(ActivityLog(actor_id=bookie2_id, action="bookie2.secret.action"))
    db.commit()
    db.close()

    resp = act_client.get("/api/activity", headers={"Authorization": act_client._bookie_token})
    assert resp.status_code == 200
    actions = [e["action"] for e in resp.json()]
    assert "bookie2.secret.action" not in actions


# ===========================================================================
# Step 4 — Unauthenticated request -> 401
# ===========================================================================

def test_get_activity_unauthenticated_returns_401(act_client):
    """GET /api/activity without a token must return 401."""
    resp = act_client.get("/api/activity")
    assert resp.status_code == 401


# ===========================================================================
# Step 5 — Append-only: no PUT/PATCH/DELETE routes for /api/activity
# ===========================================================================

def test_no_mutating_routes_exist_for_activity():
    """The activity log is append-only per entry.

    No PUT/PATCH routes may exist, and the only DELETE permitted is the
    collection-level admin "clear activity" endpoint (DELETE /api/activity).
    Individual entries can never be edited or deleted.
    """
    from app.main import create_app
    application = create_app()
    bad_methods = {"PUT", "PATCH", "DELETE"}
    for route in application.routes:
        if hasattr(route, "path") and "/activity" in route.path:
            overlap = set(route.methods or []) & bad_methods
            # Allow only the collection-level clear endpoint to expose DELETE.
            if route.path == "/api/activity":
                overlap -= {"DELETE"}
            assert not overlap, (
                f"Mutating route found at {route.path} with methods {route.methods}"
            )


# ===========================================================================
# Step 6 — Retrofit: POST /api/auth/login emits 'user.login'
# ===========================================================================

def test_login_emits_user_login_activity_entry(act_client):
    """A successful login must insert a 'user.login' ActivityLog entry."""
    from app.models.activity import ActivityLog

    resp = act_client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "adminpass"},
    )
    assert resp.status_code == 200, resp.text

    db = act_client._db_session()
    entry = (
        db.query(ActivityLog)
        .filter_by(action="user.login", actor_id=act_client._admin_id)
        .first()
    )
    assert entry is not None, "Expected a 'user.login' activity log entry"
    assert entry.target_type == "user"
    assert entry.target_id == act_client._admin_id
    db.close()


def test_failed_login_does_not_emit_activity_entry(act_client):
    """A failed login (wrong password) must NOT insert any activity log entry."""
    from app.models.activity import ActivityLog

    resp = act_client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401

    db = act_client._db_session()
    count = db.query(ActivityLog).filter_by(action="user.login").count()
    assert count == 0
    db.close()


# ===========================================================================
# Step 7 — Retrofit: POST /api/invites emits 'bookie.invited'
# ===========================================================================

def test_invite_emits_bookie_invited_activity_entry(act_client, caplog):
    """Creating an invite must emit a 'bookie.invited' ActivityLog entry."""
    from app.models.activity import ActivityLog

    with caplog.at_level(logging.INFO, logger="app.email"):
        resp = act_client.post(
            "/api/invites",
            json={"name": "Log Test Bookie", "email": "logtest@test.com"},
            headers={"Authorization": act_client._admin_token},
        )
    assert resp.status_code == 201, resp.text
    new_user_id = resp.json()["id"]

    db = act_client._db_session()
    entry = db.query(ActivityLog).filter_by(action="bookie.invited").first()
    assert entry is not None, "Expected a 'bookie.invited' activity log entry"
    assert entry.actor_id == act_client._admin_id
    assert entry.target_id == new_user_id
    assert entry.target_type == "user"
    db.close()


# ===========================================================================
# Step 8 — Retrofit: POST /api/invites/set-password emits 'bookie.activated'
# ===========================================================================

def test_set_password_emits_bookie_activated_activity_entry(act_client, caplog):
    """A successful set-password must emit a 'bookie.activated' ActivityLog entry."""
    from app.models.activity import ActivityLog
    from app.models.invite import InviteToken

    # 1. Invite a new bookie
    with caplog.at_level(logging.INFO, logger="app.email"):
        resp = act_client.post(
            "/api/invites",
            json={"name": "Activate Test", "email": "activate@test.com"},
            headers={"Authorization": act_client._admin_token},
        )
    assert resp.status_code == 201, resp.text
    new_user_id = resp.json()["id"]

    # 2. Grab the raw token from DB
    db = act_client._db_session()
    token_row = db.query(InviteToken).filter_by(user_id=new_user_id).first()
    token_str = token_row.token
    db.close()

    # 3. Set password
    resp2 = act_client.post(
        "/api/invites/set-password",
        json={"token": token_str, "password": "activated99"},
    )
    assert resp2.status_code == 200, resp2.text

    # 4. Check activity log
    db = act_client._db_session()
    entry = (
        db.query(ActivityLog)
        .filter_by(action="bookie.activated", actor_id=new_user_id)
        .first()
    )
    assert entry is not None, "Expected a 'bookie.activated' activity log entry"
    assert entry.target_type == "user"
    assert entry.target_id == new_user_id
    db.close()
