"""
Unit tests for JWT auth utilities.
"""

import pytest
from jose import JWTError

from backend.auth.jwt_handler import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    verify_password,
    verify_refresh_token,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("mysecret")
        assert verify_password("mysecret", hashed)
        assert not verify_password("wrong", hashed)

    def test_hash_is_not_plaintext(self):
        hashed = hash_password("mysecret")
        assert hashed != "mysecret"


class TestAccessToken:
    def test_create_and_decode(self):
        token = create_access_token(user_id=42, role="admin")
        payload = decode_access_token(token)
        assert payload["sub"] == "42"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_invalid_token_raises(self):
        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.token")

    def test_wrong_type_raises(self):
        from jose import jwt
        from backend.config import JWT_ALGORITHM, JWT_SECRET
        payload = {"sub": "1", "type": "refresh"}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(JWTError):
            decode_access_token(token)


class TestRefreshToken:
    def test_generate_and_verify(self):
        raw, hashed = generate_refresh_token()
        assert raw != hashed
        assert verify_refresh_token(raw, hashed)
        assert not verify_refresh_token("wrong", hashed)

    def test_two_tokens_are_different(self):
        raw1, _ = generate_refresh_token()
        raw2, _ = generate_refresh_token()
        assert raw1 != raw2
