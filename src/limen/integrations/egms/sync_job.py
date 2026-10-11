"""EGMS per AOI: tile → mosaico → celle → `cell_insar_features`.

Una volta per release (annuale), da `limen sync-egms`. Idempotente sul
registro `dataset_versions`: la versione è l'impronta delle tile usate più
la release, e una AOI che la trova già registrata non riscrive niente.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date
from functools import partial
from pathlib import Path

from limen.config.settings import EgmsSettings, Settings, get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import cell_insar_features_repo, dataset_versions_repo
from limen.integrations.egms import client, clms
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


IdRicerca = Callable[[client.Tile, str, str], Awaitable[str | None]]


def _ricerche(s: EgmsSettings) -> IdRicerca | None:
    """Chi dà l'id di ricerca per una tile: la chiave CLMS, o il token fisso."""
    if s.service_key is not None:
        chiave = clms.leggi_chiave(s.service_key.get_secret_value())
        if chiave is not None:
            return clms.Sessione(chiave, archivio=s.archive_url).cerca
    if s.token is not None and s.token.get_secret_value().strip():
        fisso = s.token.get_secret_value().strip()

        async def _token(_tile: client.Tile, _componente: str, _release: str) -> str:
            return fisso

        return _token
    return None


def _periodo(release: str) -> tuple[date, date]:
    inizio, fine = release.split("_")
    return date(int(inizio), 1, 1), date(int(fine), 12, 31)


async def sync_egms(*, aoi_id: str, settings: Settings | None = None) -> int:
    """Aggiorna `cell_insar_features` per un'AOI. Restituisce le righe scritte."""
    s = (settings or get_settings()).egms
    id_ricerca = _ricerche(s)
    if id_ricerca is None:
        log.info("egms.sync.skip", aoi_id=aoi_id, reason="né EGMS__SERVICE_KEY né EGMS__TOKEN")
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
    tiff: dict[str, list[Path]] = {}
    for componente in client.COMPONENTI:
        tiff[componente] = []
        for tile in client.tile_per_limiti(minx, miny, maxx, maxy):
            path = await client.scarica_tile(
                cartella,
                tile,
                componente,
                release=s.release,
                archivio=s.archive_url,
                id_ricerca=partial(id_ricerca, tile, componente, s.release),
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


__all__ = ["controlla_release", "sync_egms"]


async def controlla_release(settings: Settings | None = None) -> dict[str, object]:
    """C'è una release EGMS più nuova di quella configurata?

    Per il passo notturno: una sola richiesta, e solo con la chiave CLMS
    (senza login l'archivio non dice niente). Una release nuova si segnala,
    non si scarica: sono ~7 GB e un'ora, e la si sceglie in `EGMS__RELEASE`.
    """
    s = (settings or get_settings()).egms
    chiave = clms.leggi_chiave(s.service_key.get_secret_value()) if s.service_key else None
    if chiave is None:
        return {"status": "skipped", "reason": "EGMS__SERVICE_KEY non impostata"}
    disponibili = await clms.Sessione(chiave, archivio=s.archive_url).release()
    configurata = clms.release_archivio(s.release)
    ultima = max(disponibili) if disponibili else None
    if ultima is not None and ultima > configurata:
        log.warning(
            "egms.release.nuova",
            configurata=configurata,
            disponibile=ultima,
            azione=f"EGMS__RELEASE={ultima.replace('-', '_')} e poi `limen sync-egms`",
        )
        return {"status": "nuova_release", "configurata": configurata, "disponibile": ultima}
    return {"status": "ok", "configurata": configurata, "disponibile": ultima}
