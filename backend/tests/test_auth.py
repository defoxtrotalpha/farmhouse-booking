"""Auth slice tests — TDD vertical slice (Login & session).

Tests are added incrementally as behaviors are implemented.
Each section is marked with the TDD step that introduced it.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Step 1: password hashing helpers
# ---------------------------------------------------------------------------

def test_hash_password_returns_bcrypt_string():
    from app.security import hash_password
    hashed = hash_password("secret123")
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")


def test_verify_password_correct():
    from app.security import hash_password, verify_password
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_password_wrong():
    from app.security import hash_password, verify_password
    h = hash_password("hunter2")
    assert verify_password("wrong", h) is False


# ---------------------------------------------------------------------------
# Step 2: JWT access + refresh token creation / decode
# ---------------------------------------------------------------------------

def test_access_token_decodes_correctly():
    from app.security import create_access_token, decode_token
    token = create_access_token(user_id=1, role="admin")
    payload = decode_token(token)
    assert payload["sub"] == "1"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token_decodes_correctly():
    from app.security import create_refresh_token, decode_token
    token = create_refresh_token(user_id=2, role="bookie")
    payload = decode_token(token)
    assert payload["sub"] == "2"
    assert payload["role"] == "bookie"
    assert payload["type"] == "refresh"


def test_decode_token_raises_on_garbage():
    from jose import JWTError
    from app.security import decode_token
    import pytest
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")


# ---------------------------------------------------------------------------
# Step 3: User SQLAlchemy model (in-memory DB)
# ---------------------------------------------------------------------------

import pytest
from datetime import timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def mem_db():
    """Isolated in-memory SQLite + all tables for auth tests."""
    from app.db import Base
    import app.models  # noqa: ensure all models registered
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    yield db
    db.close()
    engine.dispose()


def test_user_model_can_be_created(mem_db):
    from app.models.user import User
    from datetime import datetime, timezone
    u = User(
        email="admin@farmhouse.local",
        name="Admin",
        password_hash="hashed",
        role="admin",
        is_active=True,
    )
    mem_db.add(u)
    mem_db.commit()
    mem_db.refresh(u)
    assert u.id is not None
    assert u.email == "admin@farmhouse.local"
    assert u.role == "admin"
    assert u.created_at is not None
    assert u.created_at.tzinfo is not None  # timezone-aware


# ---------------------------------------------------------------------------
# Step 4: seed_admin — idempotent admin creation
# ---------------------------------------------------------------------------

def test_seed_admin_creates_user(mem_db):
    from app.seed import seed_admin
    from app.models.user import User
    seed_admin(mem_db)
    user = mem_db.query(User).filter_by(email="admin@farmhouse.local").first()
    assert user is not None
    assert user.role == "admin"
    assert user.password_hash is not None


def test_seed_admin_is_idempotent(mem_db):
    from app.seed import seed_admin
    from app.models.user import User
    seed_admin(mem_db)
    seed_admin(mem_db)  # second call must not raise or duplicate
    count = mem_db.query(User).filter_by(email="admin@farmhouse.local").count()
    assert count == 1


# ---------------------------------------------------------------------------
# Shared fixture: isolated DB + TestClient for endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def auth_client():
    """TestClient with a fresh in-memory DB wired via dependency_overrides."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from fastapi.testclient import TestClient
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa

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

    with TestClient(application) as c:
        # expose a db session for test setup
        db = TestSession()
        c.db = db  # type: ignore[attr-defined]
        yield c
        db.close()

    eng.dispose()


# ---------------------------------------------------------------------------
# Step 5: POST /api/auth/login — success
# ---------------------------------------------------------------------------

def test_login_success(auth_client):
    from app.models.user import User
    from app.security import hash_password
    u = User(email="admin@example.com", name="Admin", password_hash=hash_password("pass123"), role="admin", is_active=True)
    auth_client.db.add(u)
    auth_client.db.commit()

    resp = auth_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "pass123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


# ---------------------------------------------------------------------------
# Step 6: login edge cases
# ---------------------------------------------------------------------------

def test_login_wrong_password_returns_401(auth_client):
    from app.models.user import User
    from app.security import hash_password
    u = User(email="bookie1@example.com", name="Bookie", password_hash=hash_password("correct"), role="bookie", is_active=True)
    auth_client.db.add(u)
    auth_client.db.commit()

    resp = auth_client.post("/api/auth/login", json={"email": "bookie1@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_disabled_user_returns_403(auth_client):
    from app.models.user import User
    from app.security import hash_password
    u = User(email="disabled@example.com", name="Dis", password_hash=hash_password("pass"), role="bookie", is_active=False)
    auth_client.db.add(u)
    auth_client.db.commit()

    resp = auth_client.post("/api/auth/login", json={"email": "disabled@example.com", "password": "pass"})
    assert resp.status_code == 403


def test_login_null_password_hash_returns_401(auth_client):
    from app.models.user import User
    u = User(email="nopw@example.com", name="NoPw", password_hash=None, role="bookie", is_active=True)
    auth_client.db.add(u)
    auth_client.db.commit()

    resp = auth_client.post("/api/auth/login", json={"email": "nopw@example.com", "password": "anything"})
    assert resp.status_code == 401


def test_login_unknown_email_returns_401(auth_client):
    resp = auth_client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "x"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Step 7: POST /api/auth/refresh
# ---------------------------------------------------------------------------

def test_refresh_success(auth_client):
    from app.models.user import User
    from app.security import hash_password, create_refresh_token
    u = User(email="ref@example.com", name="Ref", password_hash=hash_password("p"), role="bookie", is_active=True)
    auth_client.db.add(u)
    auth_client.db.commit()
    auth_client.db.refresh(u)
    rt = create_refresh_token(u.id, u.role)

    resp = auth_client.post("/api/auth/refresh", json={"refresh_token": rt})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert "refresh_token" not in body  # refresh endpoint only returns access token


def test_refresh_with_access_token_rejected(auth_client):
    from app.models.user import User
    from app.security import hash_password, create_access_token
    u = User(email="ref2@example.com", name="Ref2", password_hash=hash_password("p"), role="bookie", is_active=True)
    auth_client.db.add(u)
    auth_client.db.commit()
    auth_client.db.refresh(u)
    at = create_access_token(u.id, u.role)

    resp = auth_client.post("/api/auth/refresh", json={"refresh_token": at})
    assert resp.status_code == 401


def test_refresh_invalid_token_rejected(auth_client):
    resp = auth_client.post("/api/auth/refresh", json={"refresh_token": "garbage.token.here"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Step 8: GET /api/auth/me
# ---------------------------------------------------------------------------

def test_me_authorized(auth_client):
    from app.models.user import User
    from app.security import hash_password, create_access_token
    u = User(email="me@example.com", name="Me User", password_hash=hash_password("p"), role="admin", is_active=True)
    auth_client.db.add(u)
    auth_client.db.commit()
    auth_client.db.refresh(u)
    at = create_access_token(u.id, u.role)

    resp = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {at}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "me@example.com"
    assert body["name"] == "Me User"
    assert body["role"] == "admin"
    assert "id" in body


def test_me_no_token_returns_401(auth_client):
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 403  # HTTPBearer returns 403 when no credentials


def test_me_invalid_token_returns_401(auth_client):
    resp = auth_client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Step 9: require_admin dependency
# ---------------------------------------------------------------------------

def test_require_admin_allows_admin(auth_client):
    """Attach require_admin to a test route and verify admin passes."""
    from app.models.user import User
    from app.security import hash_password, create_access_token
    from app.dependencies import require_admin
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db import Base, get_db
    import app.models  # noqa

    # Build a minimal app with a protected route
    mini_eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(mini_eng)
    MiniSession = sessionmaker(bind=mini_eng)

    def mini_db():
        db = MiniSession()
        try:
            yield db
        finally:
            db.close()

    mini_app = FastAPI()
    mini_app.dependency_overrides[get_db] = mini_db

    @mini_app.get("/admin-only")
    def admin_route(user: User = pytest.importorskip("fastapi").Depends(require_admin)):
        return {"ok": True}

    with TestClient(mini_app) as tc:
        db = MiniSession()
        u = User(email="adm@x.com", name="A", password_hash="h", role="admin", is_active=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        at = create_access_token(u.id, u.role)
        db.close()

        resp = tc.get("/admin-only", headers={"Authorization": f"Bearer {at}"})
        assert resp.status_code == 200


def test_require_admin_blocks_bookie(auth_client):
    from app.models.user import User
    from app.security import hash_password, create_access_token
    from app.dependencies import require_admin
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db import Base, get_db
    import app.models  # noqa

    mini_eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(mini_eng)
    MiniSession = sessionmaker(bind=mini_eng)

    def mini_db():
        db = MiniSession()
        try:
            yield db
        finally:
            db.close()

    mini_app = FastAPI()
    mini_app.dependency_overrides[get_db] = mini_db

    @mini_app.get("/admin-only")
    def admin_route(user: User = pytest.importorskip("fastapi").Depends(require_admin)):
        return {"ok": True}

    with TestClient(mini_app) as tc:
        db = MiniSession()
        u = User(email="bk@x.com", name="B", password_hash="h", role="bookie", is_active=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        at = create_access_token(u.id, u.role)
        db.close()

        resp = tc.get("/admin-only", headers={"Authorization": f"Bearer {at}"})
        assert resp.status_code == 403
