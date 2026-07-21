"""Auth primitives — password hashing + codes/session tokens (pure, no DB)."""

from __future__ import annotations

from limen.auth.passwords import hash_password, verify_password
from limen.auth.tokens import (
    generate_code,
    hash_code,
    new_session_token,
    session_id,
    verify_code,
)
from limen.config.settings import AuthSettings

_FAST = AuthSettings(scrypt_n=2**14)


def test_password_roundtrip_and_rejection() -> None:
    enc = hash_password("correct horse battery", _FAST)
    assert enc.startswith("scrypt$")
    assert verify_password("correct horse battery", enc)
    assert not verify_password("wrong", enc)
    assert not verify_password("correct horse battery", None)
    assert not verify_password("x", "not-a-scrypt-hash")


def test_password_salt_is_random() -> None:
    assert hash_password("same", _FAST) != hash_password("same", _FAST)


def test_code_generation_and_verification() -> None:
    code = generate_code(6)
    assert len(code) == 6 and code.isdigit()
    h = hash_code(code)
    assert verify_code(code, h)
    assert verify_code(f" {code} ", h)  # whitespace tolerant
    assert not verify_code("000000", hash_code("111111"))


def test_session_id_is_stable_hash_of_token() -> None:
    token = new_session_token()
    assert session_id(token) == session_id(token)
    assert session_id(token) != token  # cookie carries token, DB stores its hash
    assert new_session_token() != new_session_token()
