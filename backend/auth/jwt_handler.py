"""
JWT creation and validation.
Access tokens: short-lived (15 min), contain user_id + role.
Refresh tokens: opaque random strings stored as bcrypt hashes in the DB.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    JWT_SECRET,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ──────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Access token ──────────────────────────────────────────────────────────

def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate an access token.
    Raises JWTError on invalid/expired tokens.
    """
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    return payload


# ── Refresh token ─────────────────────────────────────────────────────────

def generate_refresh_token() -> tuple[str, str]:
    """
    Returns (raw_token, hashed_token).
    Store only the hash; send the raw token to the client.
    """
    raw = secrets.token_urlsafe(64)
    hashed = pwd_context.hash(raw)
    return raw, hashed


def verify_refresh_token(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
