"""The ``hazards`` lookup table and the drift check against the settings.

Two copies of the same truth exist by necessity. ``mv_latest_risk``
cross-joins this table to produce one row per (cell, enabled hazard), and a
materialised view cannot read application settings; the Python side needs the
list without a round trip on every scoring decision. So the database owns the
view's shape and ``HAZARDS__ENABLED`` owns the code's, and something has to
notice when they disagree.

That something is a **warning**, not a refusal. During a deploy one side
moves before the other, and a public read-only map must keep serving through
the gap.
"""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.data.db import acquire

log = get_logger(__name__)


async def enabled_hazards() -> frozenset[HazardType]:
    """Hazards flagged enabled in the database."""
    async with acquire() as conn:
        rows = await conn.fetch("SELECT hazard FROM hazards WHERE enabled ORDER BY hazard")
    return frozenset(HazardType(r["hazard"]) for r in rows)


async def warn_on_config_drift(configured: list[HazardType] | frozenset[HazardType]) -> bool:
    """Compare ``HAZARDS__ENABLED`` with the database. ``True`` when they drift.

    Best-effort: an unreachable database is not this function's problem to
    report, so it degrades to "no drift detected" and logs.
    """
    wanted = frozenset(configured)
    try:
        in_db = await enabled_hazards()
    except Exception as exc:
        log.warning(
            "hazards.drift_check_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return False

    if wanted == in_db:
        return False

    log.warning(
        "hazards.config_drift",
        settings=sorted(h.value for h in wanted),
        database=sorted(h.value for h in in_db),
        only_in_settings=sorted(h.value for h in wanted - in_db),
        only_in_database=sorted(h.value for h in in_db - wanted),
    )
    return True


__all__ = ["enabled_hazards", "warn_on_config_drift"]
