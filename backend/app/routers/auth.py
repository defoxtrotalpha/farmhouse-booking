"""Auth router: login, refresh, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (

    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services.activity import log_activity
from app.dependencies import get_current_user
from app.models.user import User as UserModel
from app.tenancy import slugify

router = APIRouter(prefix="/api/auth", tags=["auth"])

_bearer = HTTPBearer()


def _me_response(db: Session, user: User) -> MeResponse:
    tenant = db.get(Tenant, user.tenant_id) if user.tenant_id is not None else None
    return MeResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        name=user.name,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_name=tenant.name if tenant else None,
        tenant_slug=tenant.slug if tenant else None,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # Resolve the user by whichever identifier was supplied.
    user: User | None = None
    if body.username:
        ident = body.username.strip()
        user = db.query(User).filter(User.username == ident).first()
    elif body.email:
        ident = body.email.lower().strip()
        user = db.query(User).filter(User.email == ident).first()
    elif body.identifier:
        ident = body.identifier.strip()
        user = (
            db.query(User)
            .filter((User.username == ident) | (User.email == ident.lower()))
            .first()
        )

    if user is None or user.password_hash is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    # Company-approval gating: members of a real company can only sign in once
    # that company is approved. Global admins (tenant_id IS NULL) and the
    # implicit single-tenant test space (also NULL) bypass this check.
    tenant = db.get(Tenant, user.tenant_id) if user.tenant_id is not None else None
    if tenant is not None and tenant.status != "approved":
        if tenant.status == "rejected":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This company's registration was declined.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This company is awaiting approval by the platform administrator.")

    # If a company name was supplied, it must match the user's tenant.
    if body.tenant and body.tenant.strip():
        if tenant is None:
            # Global admins have no company; ignore a supplied company name.
            if user.role != "global_admin":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        else:
            wanted = slugify(body.tenant)
            allowed = {tenant.slug.lower(), tenant.name.strip().lower(), slugify(tenant.name)}
            if wanted not in allowed and body.tenant.strip().lower() != tenant.name.strip().lower():
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    log_activity(
        db,
        actor_id=user.id,
        action="user.login",
        target_type="user",
        target_id=user.id,
    )
    db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
    )


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> SignupResponse:
    """Submit a request to create a new company.

    The company is created in a ``pending`` state with its first admin account
    inactive. Neither can sign in until a global admin approves the company.
    """
    company_name = (body.company_name or "").strip()
    email = (body.email or "").lower().strip()
    if not company_name:
        raise HTTPException(status_code=422, detail="Company name is required")
    if not email:
        raise HTTPException(status_code=422, detail="Email is required")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    base_slug = slugify(company_name)
    slug = base_slug
    n = 2
    while db.query(Tenant).filter(Tenant.slug == slug).first() is not None:
        slug = f"{base_slug}-{n}"
        n += 1

    tenant = Tenant(name=company_name, slug=slug, status="pending")
    db.add(tenant)
    db.flush()

    admin = User(
        tenant_id=tenant.id,
        email=email,
        username=None,
        name=body.name or "Admin",
        password_hash=hash_password(body.password),
        role="admin",
        is_active=False,  # activated on approval
    )
    db.add(admin)
    db.flush()

    log_activity(
        db,
        actor_id=admin.id,
        action="company.requested",
        target_type="tenant",
        target_id=tenant.id,
        tenant_id=tenant.id,
    )
    db.commit()

    return SignupResponse(
        status="pending",
        message="Your company request has been submitted. You'll be able to sign in once the platform administrator approves it.",
    )


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Change the signed-in user's own password (verifies current password)."""
    if current_user.password_hash is None or not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters")

    current_user.password_hash = hash_password(body.new_password)
    log_activity(
        db,
        actor_id=current_user.id,
        action="user.password_changed",
        target_type="user",
        target_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    db.commit()
    return {"ok": True}


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> AccessTokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    user_id = int(payload["sub"])
    user: User | None = db.query(User).filter_by(id=user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return AccessTokenResponse(access_token=create_access_token(user.id, user.role))


@router.get("/me", response_model=MeResponse)
def me(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> MeResponse:
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")

    user_id = int(payload["sub"])
    user: User | None = db.query(User).filter_by(id=user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return _me_response(db, user)
