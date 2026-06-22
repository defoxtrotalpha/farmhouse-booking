"""Policy / Terms management — TDD vertical slice (GitHub #31).

Tests added ONE behaviour at a time (Red -> Green).
All DB tests use an isolated in-memory SQLite via dependency_overrides.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_client():
    """Return a fresh TestClient backed by a new in-memory SQLite DB."""
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa — registers all models (including Policy) with Base.metadata

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
    client._db_session = TestSession  # type: ignore[attr-defined]
    return client


def _seed_users(session_factory):
    """Create one admin + one bookie, return (admin_token, bookie_token)."""
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
    bookie = User(
        email="bookie@test.com",
        name="Bookie",
        password_hash=hash_password("bookiepass"),
        role="bookie",
        is_active=True,
    )
    db.add_all([admin, bookie])
    db.commit()
    db.refresh(admin)
    db.refresh(bookie)
    admin_token = create_access_token(user_id=admin.id, role="admin")
    bookie_token = create_access_token(user_id=bookie.id, role="bookie")
    db.close()
    return f"Bearer {admin_token}", f"Bearer {bookie_token}"


# ---------------------------------------------------------------------------
# Test 1 — admin create sets version=1, returns 201
# ---------------------------------------------------------------------------

def test_admin_create_policy_sets_version_1():
    client = _make_client()
    admin_tok, _ = _seed_users(client._db_session)

    r = client.post(
        "/api/policies",
        json={"title": "Privacy Policy", "body": "We respect your privacy."},
        headers={"Authorization": admin_tok},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Privacy Policy"
    assert data["body"] == "We respect your privacy."
    assert data["version"] == 1
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


# ---------------------------------------------------------------------------
# Test 2 — bookie create is blocked (403)
# ---------------------------------------------------------------------------

def test_bookie_create_policy_blocked():
    client = _make_client()
    _, bookie_tok = _seed_users(client._db_session)

    r = client.post(
        "/api/policies",
        json={"title": "T&C", "body": "Terms text."},
        headers={"Authorization": bookie_tok},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Test 3 — any authenticated user can list policies
# ---------------------------------------------------------------------------

def test_authenticated_user_can_list_policies():
    client = _make_client()
    admin_tok, bookie_tok = _seed_users(client._db_session)

    # seed one policy as admin
    client.post(
        "/api/policies",
        json={"title": "Privacy Policy", "body": "Body text."},
        headers={"Authorization": admin_tok},
    )

    # both admin and bookie can list
    for tok in (admin_tok, bookie_tok):
        r = client.get("/api/policies", headers={"Authorization": tok})
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["title"] == "Privacy Policy"


# ---------------------------------------------------------------------------
# Test 4 — any authenticated user can get single policy by id
# ---------------------------------------------------------------------------

def test_authenticated_user_can_get_policy_by_id():
    client = _make_client()
    admin_tok, bookie_tok = _seed_users(client._db_session)

    create_r = client.post(
        "/api/policies",
        json={"title": "Terms", "body": "Terms body."},
        headers={"Authorization": admin_tok},
    )
    pid = create_r.json()["id"]

    for tok in (admin_tok, bookie_tok):
        r = client.get(f"/api/policies/{pid}", headers={"Authorization": tok})
        assert r.status_code == 200
        assert r.json()["id"] == pid
        assert r.json()["title"] == "Terms"


# ---------------------------------------------------------------------------
# Test 5 — admin PATCH edits body and bumps version to 2
# ---------------------------------------------------------------------------

def test_admin_patch_policy_bumps_version_to_2():
    client = _make_client()
    admin_tok, _ = _seed_users(client._db_session)

    create_r = client.post(
        "/api/policies",
        json={"title": "Privacy Policy", "body": "Original body."},
        headers={"Authorization": admin_tok},
    )
    assert create_r.json()["version"] == 1
    pid = create_r.json()["id"]

    r = client.patch(
        f"/api/policies/{pid}",
        json={"body": "Updated body."},
        headers={"Authorization": admin_tok},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 2
    assert r.json()["body"] == "Updated body."
    assert r.json()["title"] == "Privacy Policy"  # unchanged


# ---------------------------------------------------------------------------
# Test 6 — second admin PATCH bumps version to 3
# ---------------------------------------------------------------------------

def test_admin_patch_policy_second_edit_bumps_version_to_3():
    client = _make_client()
    admin_tok, _ = _seed_users(client._db_session)

    create_r = client.post(
        "/api/policies",
        json={"title": "Privacy Policy", "body": "v1 body."},
        headers={"Authorization": admin_tok},
    )
    pid = create_r.json()["id"]

    client.patch(
        f"/api/policies/{pid}",
        json={"body": "v2 body."},
        headers={"Authorization": admin_tok},
    )
    r = client.patch(
        f"/api/policies/{pid}",
        json={"title": "Privacy Policy v3", "body": "v3 body."},
        headers={"Authorization": admin_tok},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 3
    assert r.json()["title"] == "Privacy Policy v3"
    assert r.json()["body"] == "v3 body."


# ---------------------------------------------------------------------------
# Test 7 — bookie PATCH is blocked (403)
# ---------------------------------------------------------------------------

def test_bookie_patch_policy_blocked():
    client = _make_client()
    admin_tok, bookie_tok = _seed_users(client._db_session)

    create_r = client.post(
        "/api/policies",
        json={"title": "T&C", "body": "Body."},
        headers={"Authorization": admin_tok},
    )
    pid = create_r.json()["id"]

    r = client.patch(
        f"/api/policies/{pid}",
        json={"body": "Hacked."},
        headers={"Authorization": bookie_tok},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Test 8 — GET missing policy returns 404
# ---------------------------------------------------------------------------

def test_get_missing_policy_returns_404():
    client = _make_client()
    admin_tok, _ = _seed_users(client._db_session)

    r = client.get("/api/policies/9999", headers={"Authorization": admin_tok})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Test 9 — activity entry 'policy.updated' emitted on PATCH
# ---------------------------------------------------------------------------

def test_policy_updated_activity_emitted_on_patch():
    client = _make_client()
    admin_tok, _ = _seed_users(client._db_session)

    create_r = client.post(
        "/api/policies",
        json={"title": "T&C", "body": "Initial."},
        headers={"Authorization": admin_tok},
    )
    pid = create_r.json()["id"]

    client.patch(
        f"/api/policies/{pid}",
        json={"body": "Edited."},
        headers={"Authorization": admin_tok},
    )

    # read activity log as admin
    r = client.get("/api/activity", headers={"Authorization": admin_tok})
    assert r.status_code == 200
    actions = [entry["action"] for entry in r.json()]
    assert "policy.updated" in actions

    # verify target_type and target_id
    updated_entry = next(e for e in r.json() if e["action"] == "policy.updated")
    assert updated_entry["target_type"] == "policy"
    assert updated_entry["target_id"] == pid


# ---------------------------------------------------------------------------
# Test 10 — activity entry 'policy.created' emitted on POST
# ---------------------------------------------------------------------------

def test_policy_created_activity_emitted_on_post():
    client = _make_client()
    admin_tok, _ = _seed_users(client._db_session)

    create_r = client.post(
        "/api/policies",
        json={"title": "T&C", "body": "Initial."},
        headers={"Authorization": admin_tok},
    )
    assert create_r.status_code == 201
    pid = create_r.json()["id"]

    r = client.get("/api/activity", headers={"Authorization": admin_tok})
    assert r.status_code == 200
    actions = [entry["action"] for entry in r.json()]
    assert "policy.created" in actions

    created_entry = next(e for e in r.json() if e["action"] == "policy.created")
    assert created_entry["target_type"] == "policy"
    assert created_entry["target_id"] == pid
