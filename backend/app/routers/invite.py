"""Invite-a-bookie router.

Routes:
  POST /api/invites            (require_admin) → 201 InviteResponse | 409
  POST /api/invites/set-password  (public)     → 200 | 400 | 422
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.dependencies import require_admin
from app.models.invite import InviteToken
from app.models.user import User
from app.schemas.invite import InviteRequest, InviteResponse, SetPasswordRequest
from app.security import hash_password
from app.services.activity import log_activity
from app.services.email import EmailMessage, get_email_sender

router = APIRouter(prefix="/api", tags=["invites"])


@router.post("/invites", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> User:
    settings = get_settings()
    email = body.email.lower()

    # 409 if email already registered
    existing = db.query(User).filter_by(email=email).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Create invited (inactive) user with no password
    user = User(
        email=email,
        name=body.name,
        password_hash=None,
        role="bookie",
        is_active=False,
    )
    db.add(user)
    db.flush()  # assign user.id without committing

    # Create single-use expiring invite token
    token_str = InviteToken.generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.invite_token_hours)
    invite = InviteToken(user_id=user.id, token=token_str, expires_at=expires_at)
    db.add(invite)
    log_activity(
        db,
        actor_id=_admin.id,
        action="bookie.invited",
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    db.refresh(user)

    # Send invite email (token goes only into the email link, not the response)
    set_password_url = f"{settings.frontend_origin}/set-password?token={token_str}"
    sender = get_email_sender()
    sender.send(
        EmailMessage(
            to=[email],
            subject="You've been invited to Farmhouse Booking",
            body=(
                f"Hello {body.name},\n\n"
                f"You have been invited to join Farmhouse Booking as a bookie.\n"
                f"Click the link below to set your password and activate your account:\n\n"
                f"{set_password_url}\n\n"
                f"This link expires in {settings.invite_token_hours} hours.\n"
            ),
        )
    )

    return user


@router.post("/invites/set-password", status_code=status.HTTP_200_OK)
def set_password(body: SetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)

    invite: InviteToken | None = db.query(InviteToken).filter_by(token=body.token).first()

    if invite is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    if invite.used_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token has already been used")
    if invite.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token has expired")

    # Activate user and set password
    user: User | None = db.query(User).filter_by(id=invite.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    user.password_hash = hash_password(body.password)
    user.is_active = True
    invite.used_at = now
    log_activity(
        db,
        actor_id=user.id,
        action="bookie.activated",
        target_type="user",
        target_id=user.id,
    )
    db.commit()

    return {"detail": "Password set successfully. You can now log in."}
