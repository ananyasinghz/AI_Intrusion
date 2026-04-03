"""
FastAPI dependency functions for authentication and authorization.

Usage:
    @router.get("/admin-only")
    def admin_route(user = Depends(require_admin)):
        ...

    @router.get("/any-logged-in-user")
    def viewer_route(user = Depends(require_viewer)):
        ...
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from backend.auth.jwt_handler import decode_access_token
from backend.database.db import get_db
from backend.database.models import User

bearer_scheme = HTTPBearer(auto_error=False)

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)
_403 = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _401
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise _401

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
    if user is None:
        raise _401
    return user


def require_viewer(user: User = Depends(get_current_user)) -> User:
    """Any authenticated active user (admin or viewer)."""
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Admin role only."""
    if user.role != "admin":
        raise _403
    return user
