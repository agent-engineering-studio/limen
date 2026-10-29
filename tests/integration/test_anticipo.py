"""La misura di `anticipo.sql` gira sul database vero (#347)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos import anticipo_repo

pytestmark = pytest.mark.integration


async def test_la_misura_dice_da_quando_ci_sono_le_partizioni(
    reset_db: None, pg_pool: object
) -> None:
    async with acquire() as conn:
        await conn.execute("SELECT ensure_partitions('risk_assessments', 3)")
        oggi = await conn.fetchval("SELECT (now() AT TIME ZONE 'UTC')::date")
    misura = await anticipo_repo.misura(
        comuni=["000000"],
        hazard=HazardType.LANDSLIDE,
        evento_at=datetime.now(UTC) - timedelta(hours=1),
        tolleranza_ore=12,
    )
    assert misura["celle"] == 0
    assert date.fromisoformat(misura["partizioni_dal"]) <= oggi
