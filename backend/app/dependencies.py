"""Reusable FastAPI dependency guards for authentication and authorization.

Usage in any router:
    from app.dependencies import get_current_user, require_admin

    @router.get("/something")
    def something(user: User = Depends(get_current_user)):
        ...

    @router.delete("/admin-only")
    def admin_only(user: User = Depends(require_admin)):
        ...
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.security import decode_token

from typing import Optional

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Decode the Bearer access token and return the active User, or raise 401."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
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

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require the authenticated user to have the 'admin' role, or raise 403."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_global_admin(user: User = Depends(get_current_user)) -> User:
    """Require the authenticated user to be a platform global admin, or raise 403.

    Global admins have no company (``tenant_id IS NULL``) and govern the whole
    deployment: creating/approving/removing companies and managing other
    global admins.
    """
    if user.role != "global_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Global admin access required")
    return user
