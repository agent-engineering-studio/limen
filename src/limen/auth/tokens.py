"""Codes + session tokens (stdlib ``secrets`` + SHA-256).

Verification codes are short numeric OTPs (low entropy) made safe by a short
TTL + attempt cap + rate limit; only their SHA-256 is stored. Session tokens
are high-entropy; the cookie carries the raw token and the DB stores its
SHA-256 (``session_id``) so a DB leak can't be replayed as a live session.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_DIGITS = "0123456789"


def generate_code(length: int) -> str:
    return "".join(secrets.choice(_DIGITS) for _ in range(length))


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def verify_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code), code_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_id(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
