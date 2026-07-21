"""Password hashing with stdlib scrypt (RFC 7914) — no third-party hasher.

The encoded form is self-describing (``scrypt$n$r$p$salt$hash``) so a future
work-factor bump verifies old hashes and can re-hash on next login. Verification
is constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from limen.config.settings import AuthSettings

_DKLEN = 32
_SALT_BYTES = 16


def _derive(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    # maxmem must exceed scrypt's ~128*n*r footprint or OpenSSL raises.
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=dklen,
        maxmem=132 * n * r * p,
    )


def hash_password(password: str, settings: AuthSettings) -> str:
    n, r, p = settings.scrypt_n, settings.scrypt_r, settings.scrypt_p
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = _derive(password, salt, n, r, p, _DKLEN)
    return f"scrypt${n}${r}${p}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algo, n_s, r_s, p_s, salt_hex, hash_hex = encoded.split("$")
        if algo != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = _derive(password, salt, n, r, p, len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)
