"""Farmhouse CRUD — TDD vertical slice.

Tests are added ONE behavior at a time (Red -> Green).
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
    admin = User(email="admin@test.com", name="Admin", password_hash=hash_password("adminpass"), role="admin", is_active=True)
    bookie = User(email="bookie@test.com", name="Bookie", password_hash=hash_password("bookiepass"), role="bookie", is_active=True)
    db.add_all([admin, bookie])
    db.commit()
    db.refresh(admin)
    db.refresh(bookie)
    admin_token = create_access_token(user_id=admin.id, role="admin")
    bookie_token = create_access_token(user_id=bookie.id, role="bookie")
    db.close()
    return f"Bearer {admin_token}", f"Bearer {bookie_token}"


# ---------------------------------------------------------------------------
# Step 1 — Farmhouse model: buffer_minutes defaults to 0
# ---------------------------------------------------------------------------

def test_farmhouse_buffer_minutes_defaults_to_zero():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    import app.models  # noqa

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    db = Session()

    from app.models.farmhouse import Farmhouse
    fh = Farmhouse(name="Green Valley")
    db.add(fh)
    db.commit()
    db.refresh(fh)

    assert fh.buffer_minutes == 0
    assert fh.status == "active"
    assert fh.description == ""


# ---------------------------------------------------------------------------
# Step 2 — POST /api/farmhouses: admin creates a farmhouse (201)
# ---------------------------------------------------------------------------

@pytest.fixture()
def farmhouse_client():
    client = _make_client()
    client._admin_token, client._bookie_token = _seed_users(client._db_session)  # type: ignore[attr-defined]
    return client


def test_admin_create_farmhouse_201(farmhouse_client):
    resp = farmhouse_client.post(
        "/api/farmhouses",
        json={"name": "Sunrise Villa", "capacity": 50, "buffer_minutes": 30},
        headers={"Authorization": farmhouse_client._admin_token},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Sunrise Villa"
    assert body["capacity"] == 50
    assert body["buffer_minutes"] == 30
    assert body["status"] == "active"
    assert body["description"] == ""
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


# ---------------------------------------------------------------------------
# Step 3 — POST /api/farmhouses: bookie is blocked (403)
# ---------------------------------------------------------------------------

def test_bookie_create_farmhouse_403(farmhouse_client):
    resp = farmhouse_client.post(
        "/api/farmhouses",
        json={"name": "Secret Villa"},
        headers={"Authorization": farmhouse_client._bookie_token},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Step 4 — GET /api/farmhouses: active-only by default
# ---------------------------------------------------------------------------

def test_list_returns_active_only_by_default(farmhouse_client):
    # Create one active, one disabled
    db = farmhouse_client._db_session()
    from app.models.farmhouse import Farmhouse
    db.add(Farmhouse(name="Active Farm", status="active"))
    db.add(Farmhouse(name="Disabled Farm", status="disabled"))
    db.commit()
    db.close()

    resp = farmhouse_client.get(
        "/api/farmhouses",
        headers={"Authorization": farmhouse_client._admin_token},
    )
    assert resp.status_code == 200
    names = [f["name"] for f in resp.json()]
    assert "Active Farm" in names
    assert "Disabled Farm" not in names


# ---------------------------------------------------------------------------
# Step 5 — GET /api/farmhouses?include_disabled=true (admin only)
# ---------------------------------------------------------------------------

def test_admin_include_disabled_returns_all(farmhouse_client):
    db = farmhouse_client._db_session()
    from app.models.farmhouse import Farmhouse
    db.add(Farmhouse(name="Farm A", status="active"))
    db.add(Farmhouse(name="Farm B", status="disabled"))
    db.commit()
    db.close()

    resp = farmhouse_client.get(
        "/api/farmhouses?include_disabled=true",
        headers={"Authorization": farmhouse_client._admin_token},
    )
    assert resp.status_code == 200
    names = [f["name"] for f in resp.json()]
    assert "Farm A" in names
    assert "Farm B" in names


# ---------------------------------------------------------------------------
# Step 6 — bookie cannot see disabled even with include_disabled=true
# ---------------------------------------------------------------------------

def test_bookie_cannot_see_disabled_with_flag(farmhouse_client):
    db = farmhouse_client._db_session()
    from app.models.farmhouse import Farmhouse
    db.add(Farmhouse(name="Public Farm", status="active"))
    db.add(Farmhouse(name="Hidden Farm", status="disabled"))
    db.commit()
    db.close()

    resp = farmhouse_client.get(
        "/api/farmhouses?include_disabled=true",
        headers={"Authorization": farmhouse_client._bookie_token},
    )
    assert resp.status_code == 200
    names = [f["name"] for f in resp.json()]
    assert "Public Farm" in names
    assert "Hidden Farm" not in names


# ---------------------------------------------------------------------------
# Step 7 — PATCH /api/farmhouses/{id}: admin disables; disappears from list
# ---------------------------------------------------------------------------

def test_admin_patch_disables_farmhouse(farmhouse_client):
    # Create via API
    create_resp = farmhouse_client.post(
        "/api/farmhouses",
        json={"name": "To Be Disabled"},
        headers={"Authorization": farmhouse_client._admin_token},
    )
    assert create_resp.status_code == 201
    fh_id = create_resp.json()["id"]

    # Disable via PATCH
    patch_resp = farmhouse_client.patch(
        f"/api/farmhouses/{fh_id}",
        json={"status": "disabled"},
        headers={"Authorization": farmhouse_client._admin_token},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "disabled"

    # Should not appear in default list
    list_resp = farmhouse_client.get(
        "/api/farmhouses",
        headers={"Authorization": farmhouse_client._admin_token},
    )
    ids = [f["id"] for f in list_resp.json()]
    assert fh_id not in ids


# ---------------------------------------------------------------------------
# Step 8 — PATCH: bookie is blocked (403)
# ---------------------------------------------------------------------------

def test_bookie_patch_farmhouse_403(farmhouse_client):
    create_resp = farmhouse_client.post(
        "/api/farmhouses",
        json={"name": "Admin Farm"},
        headers={"Authorization": farmhouse_client._admin_token},
    )
    fh_id = create_resp.json()["id"]

    resp = farmhouse_client.patch(
        f"/api/farmhouses/{fh_id}",
        json={"name": "Hijacked"},
        headers={"Authorization": farmhouse_client._bookie_token},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Step 9 — GET /api/farmhouses/{id}: 404 for missing id
# ---------------------------------------------------------------------------

def test_get_detail_404_for_missing(farmhouse_client):
    resp = farmhouse_client.get(
        "/api/farmhouses/999999",
        headers={"Authorization": farmhouse_client._admin_token},
    )
    assert resp.status_code == 404
