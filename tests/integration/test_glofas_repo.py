"""`glofas_repo` contro un PostgreSQL vero: quello che si scrive si rilegge.

Il percentile viaggia come float Python ed è `numeric(4,3)` nella tabella:
asyncpg codifica 0.9 come il numeric esatto del binario (0.90000000000000002…),
che non è uguale a 0.900. Senza il cast lato server la lettura non trovava
mai niente — lo sweep non vedeva un riferimento salvato — e nessun test lo
diceva, perché quelli unitari sostituiscono il repo.
"""

from __future__ import annotations

from datetime import date

import pytest

from limen.data.db import acquire
from limen.data.repos import glofas_repo

pytestmark = pytest.mark.integration

_NODI = [(11.9, 44.3), (12.0, 44.3), (12.1, 44.4)]


async def _pulisci() -> None:
    async with acquire() as conn:
        await conn.execute("DELETE FROM glofas_riferimento")
        await conn.execute("DELETE FROM glofas_previsione")


async def test_un_riferimento_salvato_si_rilegge(pg_pool: object) -> None:
    await _pulisci()
    await glofas_repo.salva(
        [(_NODI[0], 12.5), (_NODI[1], None), (_NODI[2], 0.0)],
        percentile=0.9,
        window_days=730,
        fonte="ewds:version_4_0",
    )

    letti = await glofas_repo.riferimenti(_NODI, percentile=0.9, window_days=730)
    assert letti == {_NODI[0]: pytest.approx(12.5), _NODI[1]: None, _NODI[2]: 0.0}
    assert await glofas_repo.con_fiume(percentile=0.9, window_days=730) == 1
    assert await glofas_repo.nodi_con_fiume(percentile=0.9, window_days=730) == [_NODI[0]]
    await _pulisci()


async def test_la_previsione_salvata_si_rilegge_dall_ultima_corsa(pg_pool: object) -> None:
    await _pulisci()
    await glofas_repo.salva_previsione(date(2026, 10, 10), {_NODI[0]: 3.0}, fonte="t")
    await glofas_repo.salva_previsione(date(2026, 10, 11), {_NODI[0]: 7.5}, fonte="t")

    assert await glofas_repo.ultima_corsa() == date(2026, 10, 11)
    assert await glofas_repo.picchi(_NODI, dal=date(2026, 10, 9)) == {_NODI[0]: 7.5}
    assert await glofas_repo.picchi(_NODI, dal=date(2026, 10, 12)) is None
    await _pulisci()
