"""La copertura si conta sulla griglia, non sulle righe dei fattori.

Il 6 novembre 2026, con venti regioni seminate e fattori per due, la pagina di
installazione e `data-status` dicevano «pronto» per tutti e tre i pericoli: una
regione senza righe in `cell_static_factors` non esisteva proprio.
"""

from __future__ import annotations

import pytest

from limen.cli.seed import run as run_seed
from limen.config.catalogo_dati import carica_catalogo
from limen.core.installazione import mancanti, regioni_senza
from limen.data.db import acquire
from limen.data.repos import copertura_repo
from tests.conftest import SEED_SMALL_AOI

pytestmark = pytest.mark.integration


async def test_una_regione_senza_fattori_non_e_pronta(pg_pool: object) -> None:
    await run_seed(only=[SEED_SMALL_AOI])
    async with acquire() as conn:
        await conn.execute("TRUNCATE cell_static_factors CASCADE")

    catalogo = carica_catalogo()
    copertura = await copertura_repo.leggi(catalogo)

    assert copertura.celle_totali > 0
    assert copertura.per_regione[SEED_SMALL_AOI]["dtm"] == 0
    assert SEED_SMALL_AOI in regioni_senza(catalogo, copertura.per_regione)["dtm"]
    assert all(
        ids
        for ids in mancanti(
            catalogo, totali=copertura.totali, per_regione=copertura.per_regione
        ).values()
    )


async def test_una_regione_caricata_a_zero_e_da_verificare(pg_pool: object) -> None:
    """Il caso Trentino (#454, #467): IFFI scritto a zero su ogni cella.

    Il conteggio dei valori lo dà caricato; quello dei valori > 0 no.
    """
    from limen.core.installazione import regioni_da_verificare

    await run_seed(only=[SEED_SMALL_AOI])
    async with acquire() as conn:
        await conn.execute("TRUNCATE cell_static_factors CASCADE")
        await conn.execute(
            "INSERT INTO cell_static_factors (cell_id, iffi_density_500) "
            "SELECT id, 0 FROM grid_cells WHERE aoi_id = $1",
            SEED_SMALL_AOI,
        )

    catalogo = carica_catalogo()
    copertura = await copertura_repo.leggi(catalogo)

    assert copertura.per_regione[SEED_SMALL_AOI]["iffi"] > 0
    assert copertura.informativi_per_regione[SEED_SMALL_AOI]["iffi"] == 0
    assert SEED_SMALL_AOI not in regioni_senza(catalogo, copertura.per_regione)["iffi"]
    sospette = regioni_da_verificare(
        catalogo,
        copertura.per_regione,
        copertura.informativi_per_regione,
        copertura.celle_per_regione,
    )
    assert sospette["iffi"] == [SEED_SMALL_AOI]
