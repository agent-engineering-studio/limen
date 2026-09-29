"""Esposizione per cella: chi e cosa c'è vicino, indipendentemente dal pericolo.

Il numero che porta un comune all'attenzione pesa il punteggio per quanto c'è
da perdere — «soprattutto in vicinanza di un centro abitato». Quel peso è
l'esposizione, che il dispacciatore degli alert calcola già per cella con una
funzione pura.

Qui viene **materializzata** in `cell_static_factors.exposure_norm`, perché il
rollup per comune è una vista materializzata e da SQL quella funzione non si
chiama: l'alternativa sarebbe riscrivere la formula in SQL, cioè avere due
copie delle stesse soglie che possono divergere.

**Senza il termine WUI.** L'interfaccia urbano-bosco pesa solo per l'incendio,
e qui serve una proprietà del *posto* — quante persone e quante strade ci sono
intorno — non del pericolo. Lasciandolo dentro, lo stesso comune avrebbe
un'esposizione diversa a seconda del pericolo guardato, che è esattamente la
confusione che il redesign toglie.

Si ricalcola solo quando cambiano i fattori statici (CORINE, OSM, DEM): è
`limen calibrate` a chiamarla, insieme al precalcolo di `s_static`.
"""

from __future__ import annotations

from typing import Any

from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD
from limen.core.scoring.exposure import exposure_factor_from_row
from limen.core.scoring.regional_thresholds import load_hazard_thresholds
from limen.data.db import acquire

log = get_logger(__name__)

#: Le colonne che l'adattatore si aspetta, con i nomi che usa.
_READ_SQL = """
SELECT cell_id,
       (landuse_code LIKE '11%') AS urban_here,
       (landuse_code LIKE '12%') AS infra_here,
       near_urban                AS urban_near,
       near_infra                AS infra_near,
       distance_to_road_m,
       distance_to_rail_m,
       nearest_road_class
FROM cell_static_factors
ORDER BY cell_id
"""


async def refresh_exposure_norm() -> int:
    """Ricalcola `exposure_norm` per ogni cella. Ritorna le righe scritte."""
    cfg = load_hazard_thresholds(DEFAULT_HAZARD).exposure
    async with acquire() as conn, conn.transaction():
        rows = await conn.fetch(_READ_SQL)
        valori: list[tuple[Any, ...]] = [
            (str(r["cell_id"]), float(exposure_factor_from_row(r, cfg)[0])) for r in rows
        ]
        # Una tabella temporanea e un solo UPDATE: trecentomila UPDATE
        # singoli sarebbero trecentomila round-trip.
        await conn.execute(
            "CREATE TEMP TABLE exposure_batch (cell_id text, exposure_norm double precision)"
            " ON COMMIT DROP"
        )
        await conn.copy_records_to_table(
            "exposure_batch", records=valori, columns=["cell_id", "exposure_norm"]
        )
        await conn.execute(
            """
            UPDATE cell_static_factors c
            SET exposure_norm = b.exposure_norm
            FROM exposure_batch b
            WHERE b.cell_id = c.cell_id
              AND c.exposure_norm IS DISTINCT FROM b.exposure_norm
            """
        )
    log.info("exposure.refreshed", cells=len(valori))
    return len(valori)
