"""``limen rain-climatology`` — com'è di solito la pioggia a 72 ore, per nodo.

Per ogni nodo del reticolo dell'alluvione (0,1°) legge dall'archivio ERA5 la
pioggia giornaliera di più anni, fa le somme mobili su tre giorni e ne salva
i quantili (migrazione 065). Da lì il motore ricava le soglie locali della
pioggia: in un posto dove 105 mm in tre giorni capitano ogni anno non sono
la stessa notizia che dove non capitano mai.

Si riprende da dove si era fermato: i nodi già fatti per lo stesso intervallo
di anni si saltano.

* ``LIMEN_RAIN_CLIM_YEARS`` — anni di archivio (default 10), fino all'ultimo
  anno intero.
* ``LIMEN_RAIN_CLIM_AOI``   — una sola AOI; assente ⇒ tutte.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

from limen.cli.fwi_backfill import _aoi_bbox, _int_env
from limen.core.logging import get_logger
from limen.core.scoring.flood.climatologia import quantili, somme_tre_giorni
from limen.data.db import lifespan_pool
from limen.data.repos import pioggia_climatologia_repo
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.data.repos.pioggia_climatologia_repo import NodoPioggia
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.flood import NODE_SPACING_DEG
from limen.integrations.openmeteo.grid import build_snapped_nodes

log = get_logger(__name__)

_LOTTO = 100
#: Un nodo con più del 5 % di giorni mancanti non si scrive: resta da fare.
_COPERTURA_MINIMA = 0.95


def riassumi(
    nodo: tuple[float, float], giornaliere: list[float | None], anno_da: int, anno_a: int
) -> NodoPioggia | None:
    """Il nodo riassunto, o ``None`` se l'archivio ha troppi buchi."""
    attesi = (date(anno_a, 12, 31) - date(anno_da, 1, 1)).days + 1
    validi = [v for v in giornaliere if v is not None]
    if len(validi) < _COPERTURA_MINIMA * attesi:
        return None
    # Un giorno mancante vale zero dentro una somma: con meno del 5 % di
    # buchi sposta i quantili alti meno dell'arrotondamento.
    somme = somme_tre_giorni([v or 0.0 for v in giornaliere])
    return NodoPioggia(
        lon=nodo[0],
        lat=nodo[1],
        giorni=len(somme),
        quantili=quantili(somme),
        anno_da=anno_da,
        anno_a=anno_a,
    )


async def run() -> int:
    quanti = max(_int_env("LIMEN_RAIN_CLIM_YEARS", 10), 1)
    anno_a = datetime.now(UTC).year - 1
    anno_da = anno_a - quanti + 1
    client = OpenMeteoHttpClient()
    scritti = 0
    async with lifespan_pool():
        una = os.getenv("LIMEN_RAIN_CLIM_AOI")
        nodi: set[tuple[float, float]] = set()
        for aoi_id in [una] if una else await list_aoi_ids():
            bbox = await _aoi_bbox(aoi_id)
            if bbox is not None:
                nodi.update(build_snapped_nodes(bbox, spacing=NODE_SPACING_DEG))
        fatti = await pioggia_climatologia_repo.nodi_fatti(anno_da, anno_a)
        da_fare = sorted(n for n in nodi if (round(n[0], 4), round(n[1], 4)) not in fatti)
        log.info("rain.climatology.start", nodes=len(nodi), to_do=len(da_fare))
        for i in range(0, len(da_fare), _LOTTO):
            lotto = da_fare[i : i + _LOTTO]
            serie = await client.get_daily_rain_grid(
                nodes=lotto, start=date(anno_da, 1, 1), end=date(anno_a, 12, 31)
            )
            righe = [
                r
                for nodo, giornaliere in zip(lotto, serie, strict=False)
                if (r := riassumi(nodo, giornaliere, anno_da, anno_a)) is not None
            ]
            scritti += await pioggia_climatologia_repo.upsert_many(righe)
            log.info(
                "rain.climatology.batch",
                done=min(i + _LOTTO, len(da_fare)),
                of=len(da_fare),
                rows=scritti,
            )
    await SharedHttpClient.aclose()
    log.info("rain.climatology.done", rows=scritti)
    return 0


__all__ = ["riassumi", "run"]
