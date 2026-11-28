"""EGMS per AOI: tile → mosaico → celle → `cell_insar_features`.

Una volta per release (annuale), da `limen sync-egms`. Idempotente sul
registro `dataset_versions`: la versione è l'impronta delle tile usate più
la release, e una AOI che la trova già registrata non riscrive niente.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

from egms_client import (
    COMPONENTS,
    Component,
    EgmsError,
    Tile,
    api_release,
    tile_prefix,
    tiles_for_bounds,
)
from egms_client.mosaic import mosaic
from egms_client.releases import window

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import cell_insar_features_repo, dataset_versions_repo
from limen.integrations.egms import clms
from limen.integrations.egms.aggregate import Cella, per_cella, su_griglia

log = get_logger(__name__)

SOURCE = "copernicus.egms"
#: Da cambiare quando cambia il modo di aggregare, non il dato.
#: v2: accelerazione e stagionalità dal CSV della tile (#380).
#: v3: statistiche di `egms_client.cells` (accelerazione verticale con segno
#: sugli stessi pixel della velocità, #700) e la finestra vera della release
#: in `period_start`/`period_end` (#699).
VERSIONE_CALCOLO = "ortho-l3-v3"


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


#: Il segnaposto del mare di prima di egms-client 0.2: ``…_2020_2025.assente``
#: o ``…_2020_2025_1.assente``. La libreria scrive ``…_2020_2025_absent``.
_VECCHIO_SEGNAPOSTO = re.compile(r"(EGMS_L3_E\d+N\d+_100km_[UE]_\d{4}_\d{4})(?:_\d+)?\.assente")


def migra_segnaposto(cartella: Path) -> int:
    """I segnaposto vecchi del mare rinominati come li cerca la libreria.

    Senza, al primo sync ogni tile in mare tornerebbe a chiedere una ricerca
    all'archivio (nessun download: la ricerca risponde «Invalid tile ID»).
    Restituisce quanti ne ha rinominati.
    """
    rinominati = 0
    for vecchio in cartella.glob("*.assente"):
        trovato = _VECCHIO_SEGNAPOSTO.fullmatch(vecchio.name)
        if trovato is None:
            continue
        nuovo = cartella / f"{trovato[1]}_absent"
        if nuovo.exists():
            vecchio.unlink()
        else:
            vecchio.rename(nuovo)
        rinominati += 1
    if rinominati:
        log.info("egms.segnaposto_migrati", n=rinominati)
    return rinominati


def _periodo(release: str) -> tuple[date | None, date | None]:
    """Prima e ultima acquisizione della release, ``None`` se non sono note.

    Il nome non è la finestra: la 2020-2025 comincia il 9 dicembre 2020, e
    scrivere il 1° gennaio metteva la misura undici mesi prima di sé (#699).
    Per una release che la libreria non ha ancora letto non si inventano date.
    """
    finestra = window(api_release(release))
    return finestra.first, finestra.last


async def sync_egms(*, aoi_id: str, settings: Settings | None = None) -> int:
    """Aggiorna `cell_insar_features` per un'AOI. Restituisce le righe scritte."""
    s = (settings or get_settings()).egms
    archivio = await clms.archivio(s)
    if archivio is None:
        log.info("egms.sync.skip", aoi_id=aoi_id, reason=clms.perche_no(s))
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
    cartella.mkdir(parents=True, exist_ok=True)
    migra_segnaposto(cartella)
    await asyncio.to_thread(clms.migra_attributi, cartella)
    richieste = [(c, t) for c in COMPONENTS for t in tiles_for_bounds(minx, miny, maxx, maxy)]
    cancello = asyncio.Semaphore(s.concorrenza)
    fallite: list[str] = []

    async def _una(componente: Component, tile: Tile) -> Path | None:
        # Una tile già sul disco (o già nota come mare) non chiede niente
        # all'archivio: il secondo sync scarica zero byte.
        async with cancello:
            try:
                # Accelerazione e stagionalità sono verticali: il CSV della
                # componente est (~250 MB a tile) non serve più (#700).
                return await clms.scarica_tile(
                    archivio, tile, componente, s.release, cartella, attributi=componente == "U"
                )
            except EgmsError as exc:
                fallite.append(tile_prefix(tile, componente, s.release))
                log.warning("egms.tile_rifiutata", aoi_id=aoi_id, error=str(exc)[:200])
                return None

    trovate = await asyncio.gather(*(_una(c, t) for c, t in richieste))
    if fallite:
        # Scrivere senza quelle tile metterebbe `scatterer_count = 0` («il
        # satellite qui non vede») sulle celle che coprono, sopra le misure
        # del sync precedente: l'AOI resta com'era e il prossimo sync la
        # riprova (le altre tile sono già sul disco). Le altre AOI vanno avanti.
        log.warning(
            "integration.degraded", source=SOURCE, aoi_id=aoi_id, tile_rifiutate=sorted(fallite)
        )
        return 0
    tiff: dict[str, list[Path]] = {c: [] for c in COMPONENTS}
    for (componente, _), path in zip(richieste, trovate, strict=True):
        if path is not None:
            tiff[componente].append(path)

    usate = sorted(p.name for ps in tiff.values() for p in ps)
    versione = dataset_versions_repo.content_hash([VERSIONE_CALCOLO, s.release, *usate])
    dataset = f"ortho_l3/{aoi_id}"
    if await dataset_versions_repo.find(SOURCE, dataset, versione) is not None:
        log.info("egms.sync.invariato", aoi_id=aoi_id, tile=len(usate))
        return 0

    limiti = {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy}
    verticale = await asyncio.to_thread(mosaic, tiff["U"], **limiti)
    est = await asyncio.to_thread(mosaic, tiff["E"], **limiti)
    attributi = [clms.attributi_di(p) for p in tiff["U"]]
    righe = await asyncio.to_thread(
        per_cella,
        celle,
        verticale,
        est,
        accelerazione=await asyncio.to_thread(su_griglia, attributi, "acceleration", verticale),
        stagionalita=await asyncio.to_thread(su_griglia, attributi, "seasonality", verticale),
    )

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
    archivio = await clms.archivio(s)
    if archivio is None:
        return {"status": "skipped", "reason": clms.perche_no(s)}
    disponibili = await clms.releases(archivio)
    configurata = api_release(s.release)
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
