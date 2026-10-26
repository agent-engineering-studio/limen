"""``limen fetch-static`` — le sorgenti statiche pubbliche, con un manifest (#305).

Scarica sotto ``LIMEN_DATA_ROOT`` quello che si ottiene senza un account:

* il suolo sigillato CLMS dall'ImageServer aperto dell'EEA
  (``sealing/clms_imd_2018/imd_2018_100m.tif``, come ``imperviousness-fetch``);
* strade principali e ferrovia da OpenStreetMap (``osm/osm_roads.gpkg``,
  ``osm/osm_rails.gpkg``, gli stessi filtri di ``make osm-data``), estratte
  dal PBF di Geofabrik con pyogrio: niente GDAL sull'host.

DTM, CORINE e geolitologia restano a mano (registrazione presso l'ente che li
pubblica): su un server nuovo li rende superflui lo snapshot statico.

``static-manifest.json``, nella stessa radice, tiene percorso, dimensione e
sha256 di ogni file scaricato. Un file presente si verifica e non si
riscarica; uno che non è più quello del manifest ferma il comando, perché un
raster troncato darebbe fattori sbagliati senza nessun errore. Lo sha256 è del
file scaricato **qui**: il riquadro dell'impermeabilizzazione viene dalle AOI
seminate e l'estratto OSM cambia ogni giorno, quindi non c'è un hash da
fissare nel repo.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.config.percorsi import radice_dati
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.imperviousness.fetch import (
    CLMS_IMD_2018_URL,
    _resolve_dest,
    fetch_imperviousness,
)

log = get_logger(__name__)

MANIFEST = "static-manifest.json"
OSM_PBF_URL_ENV = "LIMEN_OSM_PBF_URL"
OSM_PBF_URL = "https://download.geofabrik.de/europe/italy-latest.osm.pbf"
#: Gli stessi filtri di `make osm-data`: l'esposizione guarda la rete
#: principale, non ogni strada di campagna.
OSM_ESTRATTI = {
    "osm_roads.gpkg": "highway IN ('motorway','trunk','primary','secondary')",
    "osm_rails.gpkg": "railway = 'rail'",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def _leggi(radice: Path) -> dict[str, dict[str, Any]]:
    try:
        dati: dict[str, dict[str, Any]] = json.loads((radice / MANIFEST).read_text())
    except FileNotFoundError:
        return {}
    return dati


def _scrivi(radice: Path, manifest: dict[str, dict[str, Any]]) -> None:
    tmp = radice / (MANIFEST + ".part")
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    tmp.replace(radice / MANIFEST)


async def alterati(radice: Path, manifest: dict[str, dict[str, Any]]) -> list[str]:
    """I file del manifest presenti su disco ma non più quelli registrati."""
    out = []
    for rel, voce in manifest.items():
        path = radice / rel
        if not path.exists():
            continue
        if (
            path.stat().st_size != voce["byte"]
            or await asyncio.to_thread(_sha256, path) != voce["sha256"]
        ):
            out.append(rel)
    return out


def _chiave(radice: Path, path: Path) -> str:
    # Relativo alla radice, così il manifest segue la cartella se la si sposta;
    # assoluto se una variabile ha messo il file altrove.
    return str(path.relative_to(radice)) if path.is_relative_to(radice) else str(path.resolve())


async def _registra(
    radice: Path, manifest: dict[str, dict[str, Any]], path: Path, fonte: str
) -> None:
    manifest[_chiave(radice, path)] = {
        "byte": path.stat().st_size,
        "sha256": await asyncio.to_thread(_sha256, path),
        "fonte": fonte,
        "scaricato": datetime.now(UTC).isoformat(timespec="seconds"),
    }


async def _scarica(url: str, dest: Path) -> None:
    """Un file grande in streaming, su ``.part`` e poi rinominato: un download
    interrotto non lascia un PBF che sembra completo."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    client = await SharedHttpClient.get()
    async with client.stream("GET", url) as risposta:
        risposta.raise_for_status()
        with tmp.open("wb") as f:
            async for blocco in risposta.aiter_bytes(1 << 20):
                f.write(blocco)
    tmp.replace(dest)


def _estrai(pbf: Path, dest: Path, where: str) -> None:
    import pyogrio

    tabella = pyogrio.read_dataframe(pbf, layer="lines", where=where)
    tmp = dest.with_name(dest.name + ".part.gpkg")
    pyogrio.write_dataframe(tabella, tmp, driver="GPKG")
    tmp.replace(dest)


async def osm(radice: Path, manifest: dict[str, dict[str, Any]], url: str) -> None:
    cartella = radice / "osm"
    for nome in OSM_ESTRATTI:
        # Estratto prima con `make osm-data`: da qui in poi lo si verifica.
        if (cartella / nome).exists() and _chiave(radice, cartella / nome) not in manifest:
            await _registra(radice, manifest, cartella / nome, url)
    mancanti = {n: w for n, w in OSM_ESTRATTI.items() if not (cartella / n).exists()}
    if not mancanti:
        log.info("fetch_static.osm.presente")
        return
    pbf = cartella / Path(url).name
    if not pbf.exists():
        log.info("fetch_static.osm.download", url=url)
        await _scarica(url, pbf)
    for nome, where in mancanti.items():
        await asyncio.to_thread(_estrai, pbf, cartella / nome, where)
        await _registra(radice, manifest, cartella / nome, f"{url} [{where}]")
        log.info("fetch_static.osm.estratto", file=nome)


async def run() -> int:
    radice = radice_dati()
    radice.mkdir(parents=True, exist_ok=True)
    manifest = _leggi(radice)
    if rotti := await alterati(radice, manifest):
        log.error(
            "fetch_static.alterati",
            file=rotti,
            hint="non sono più quelli scaricati: cancellali e rilancia",
        )
        return 1

    async with lifespan_pool(get_settings().db):
        dest = _resolve_dest(None)
        if dest.exists() and _chiave(radice, dest) not in manifest:
            await _registra(radice, manifest, dest, CLMS_IMD_2018_URL)
        if not dest.exists():
            scritto = await fetch_imperviousness()
            if scritto is None:
                log.error(
                    "fetch_static.no_aoi", hint="prima limen seed: il riquadro viene dalle AOI"
                )
                return 1
            await _registra(radice, manifest, scritto, CLMS_IMD_2018_URL)
            _scrivi(radice, manifest)
        await osm(radice, manifest, os.environ.get(OSM_PBF_URL_ENV) or OSM_PBF_URL)
        await SharedHttpClient.aclose()
    _scrivi(radice, manifest)
    log.info("fetch_static.fatto", radice=str(radice), file=sorted(manifest))
    return 0


__all__ = ["MANIFEST", "alterati", "osm", "run"]
