"""Database-backed authentication (replaces Clerk — PA-compliant, self-hosted).

Local email+password with email-code verification; server-side sessions in an
httpOnly cookie; role gating (admin/ml-ops/operatore/viewer). SPID wiring lands
in a later phase. See issue #49 and docs/auth.md.
"""

from limen.auth.deps import RequireUser, current_user, require_role, require_session
from limen.auth.models import VALID_ROLES, AuthUser
from limen.auth.service import AuthError

__all__ = [
    "VALID_ROLES",
    "AuthError",
    "AuthUser",
    "RequireUser",
    "current_user",
    "require_role",
    "require_session",
]
