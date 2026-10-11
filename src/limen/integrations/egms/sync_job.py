"""EGMS per AOI: tile → mosaico → celle → `cell_insar_features`.

Una volta per release (annuale), da `limen sync-egms`. Idempotente sul
registro `dataset_versions`: la versione è l'impronta delle tile usate più
la release, e una AOI che la trova già registrata non riscrive niente.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import replace
from datetime import date
from pathlib import Path

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import cell_insar_features_repo, dataset_versions_repo
from limen.integrations.egms import client
from limen.integrations.egms.aggregate import PASSO_M, Cella, Griglia, mosaico, per_cella

log = get_logger(__name__)

SOURCE = "copernicus.egms"
#: Da cambiare quando cambia il modo di aggregare, non il dato.
VERSIONE_CALCOLO = "ortho-l3-v1"


async def _celle(aoi_id: str) -> list[Cella]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id,
                   ST_XMin(g) AS minx, ST_YMin(g) AS miny,
                   ST_XMax(g) AS maxx, ST_YMax(g) AS maxy
            FROM (SELECT id, ST_Transform(geom, 3035) AS g FROM grid_cells WHERE aoi_id = $1) t
            """,
            aoi_id,
        )
    return [
        Cella(
            cell_id=str(r["id"]),
            minx=float(r["minx"]),
            miny=float(r["miny"]),
            maxx=float(r["maxx"]),
            maxy=float(r["maxy"]),
        )
        for r in rows
    ]


def _periodo(release: str) -> tuple[date, date]:
    inizio, fine = release.split("_")
    return date(int(inizio), 1, 1), date(int(fine), 12, 31)


async def sync_egms(*, aoi_id: str, settings: Settings | None = None) -> int:
    """Aggiorna `cell_insar_features` per un'AOI. Restituisce le righe scritte."""
    s = (settings or get_settings()).egms
    if not s.attivo or s.token is None:
        log.info("egms.sync.skip", aoi_id=aoi_id, reason="EGMS__TOKEN non impostato")
        return 0
    celle = await _celle(aoi_id)
    if not celle:
        log.warning("egms.sync.no_cells", aoi_id=aoi_id)
        return 0
    minx = min(c.minx for c in celle)
    miny = min(c.miny for c in celle)
    maxx = max(c.maxx for c in celle)
    maxy = max(c.maxy for c in celle)

    cartella = Path(s.cartella)
    token = s.token.get_secret_value()
    tiff: dict[str, list[Path]] = {}
    for componente in client.COMPONENTI:
        tiff[componente] = []
        for tile in client.tile_per_limiti(minx, miny, maxx, maxy):
            path = await client.scarica_tile(
                cartella, tile, componente, release=s.release, url=s.download_url, token=token
            )
            if path is not None:
                tiff[componente].append(path)

    usate = sorted(p.name for ps in tiff.values() for p in ps)
    versione = dataset_versions_repo.content_hash([VERSIONE_CALCOLO, s.release, *usate])
    dataset = f"ortho_l3/{aoi_id}"
    if await dataset_versions_repo.find(SOURCE, dataset, versione) is not None:
        log.info("egms.sync.invariato", aoi_id=aoi_id, tile=len(usate))
        return 0

    limiti = {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy}
    verticale = await asyncio.to_thread(mosaico, tiff["U"], **limiti)
    est = await asyncio.to_thread(mosaico, tiff["E"], **limiti)
    # Lo stesso angolo su cui `mosaico` ha allineato la griglia.
    griglia = Griglia(
        verticale=verticale,
        est=est,
        left=math.floor(minx / PASSO_M) * PASSO_M,
        top=math.ceil(maxy / PASSO_M) * PASSO_M,
    )
    righe = await asyncio.to_thread(per_cella, celle, griglia)

    inizio, fine = _periodo(s.release)
    version_id = await dataset_versions_repo.record(
        source=SOURCE,
        dataset=dataset,
        version=versione,
        metadata={"release": s.release, "tile": usate, "calcolo": VERSIONE_CALCOLO},
    )
    scritte = await cell_insar_features_repo.upsert_many(
        [
            replace(r, period_start=inizio, period_end=fine, dataset_version_id=version_id)
            for r in righe
        ]
    )
    misurate = sum(1 for r in righe if r.scatterer_count > 0)
    log.info(
        "egms.sync.done",
        aoi_id=aoi_id,
        celle=len(celle),
        misurate=misurate,
        tile=len(usate),
        righe=scritte,
    )
    return scritte


__all__ = ["sync_egms"]
