"""
Authentication routes:
  POST /auth/login    → {access_token, refresh_token, token_type}
  POST /auth/refresh  → {access_token}
  POST /auth/logout   → revokes refresh token
  GET  /auth/me       → current user profile
  PUT  /auth/me/password → change own password
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user, require_admin
from backend.auth.jwt_handler import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    refresh_token_expiry,
    verify_password,
    verify_refresh_token,
)
from backend.database.db import get_db
from backend.database.models import RefreshToken, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response schemas ────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "viewer"


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == body.username,
        User.is_active == True,  # noqa: E712
    ).first()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(user.id, user.role)
    raw_refresh, hashed_refresh = generate_refresh_token()

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hashed_refresh,
        expires_at=refresh_token_expiry(),
    ))
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    logger.info("User '%s' logged in.", user.username)
    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "user": user.to_dict(),
    }


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    # Find all non-revoked, non-expired tokens and verify against the raw token
    candidates = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.revoked == False,  # noqa: E712
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .all()
    )

    matched: RefreshToken | None = None
    for candidate in candidates:
        if verify_refresh_token(body.refresh_token, candidate.token_hash):
            matched = candidate
            break

    if matched is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.query(User).filter(User.id == matched.user_id, User.is_active == True).first()  # noqa: E712
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Rotate refresh token
    matched.revoked = True
    raw_refresh, hashed_refresh = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hashed_refresh,
        expires_at=refresh_token_expiry(),
    ))
    db.commit()

    return {
        "access_token": create_access_token(user.id, user.role),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout(body: RefreshRequest, db: Session = Depends(get_db)):
    candidates = (
        db.query(RefreshToken)
        .filter(RefreshToken.revoked == False)  # noqa: E712
        .all()
    )
    for candidate in candidates:
        if verify_refresh_token(body.refresh_token, candidate.token_hash):
            candidate.revoked = True
            db.commit()
            return {"status": "logged_out"}

    return {"status": "token_not_found"}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user.to_dict()


@router.put("/me/password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"status": "password_updated"}
