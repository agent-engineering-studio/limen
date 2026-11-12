"""I giorni di piena di una stazione da ``flood_events``, contro un Postgres vero (#501)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from limen.cli.idrometri_misura import _giorni_di_piena
from limen.data.db import acquire
from limen.integrations.arpae.idrometri import Stazione

pytestmark = pytest.mark.integration


async def test_giorni_di_piena_entro_il_raggio(reset_db: None, pg_pool: object) -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO flood_events (id, source, activation_code, event_time, geom) VALUES "
            "('p1', 'cems', 'EMSR664', $1, "
            "ST_Multi(ST_MakeEnvelope(11.90, 44.30, 11.92, 44.32, 4326)))",
            datetime(2023, 5, 16, 12, tzinfo=UTC),
        )
    vicina = Stazione(chiave="vicina", nome="Faenza", lon=11.93, lat=44.31)
    lontana = Stazione(chiave="lontana", nome="Piacenza", lon=9.69, lat=45.05)
    piene = await _giorni_di_piena(
        [vicina, lontana], inizio=date(2023, 5, 1), fine=date(2023, 5, 31), raggio_km=5.0
    )
    assert piene == {"vicina": {date(2023, 5, 15), date(2023, 5, 16), date(2023, 5, 17)}}
