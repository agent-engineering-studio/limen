"""Inventario RER2023 delle frane di maggio 2023 in Emilia-Romagna → ``landslide_events`` (#500).

Le 80.997 frane mappate dopo le due alluvioni di maggio 2023 (Berti et al.,
*Earth System Science Data* 2025; Zenodo 10.5281/zenodo.13742643, CC BY 4.0).
Entra con ``source = 'rer2023'``, così il backtest può prenderlo o lasciarlo
con ``LIMEN_BACKTEST_SORGENTI``.

Tre scelte, dichiarate negli ``attributes``:

* **Una riga per cella**, come per Marche-Umbria: il backtest conta
  celle-giorno, e 80.997 poligoni di una settimana peserebbero più di tutto il
  resto del catalogo. Si tiene il centroide della prima frana di ogni cella,
  con ``numero_frane`` della cella.
* **Data convenzionale**: l'inventario non data le singole frane. Si assegna
  la sera del 16/05/2023 (20 locali), il picco della seconda ondata, con
  classe ``T3`` — il giorno è incerto: una parte delle frane è del 1-3 maggio.
  Deciso dal curatore il 13/11/2026.
* **Luogo** ``P1``: poligoni mappati, entro la cella.

L'archivio è un RAR (l'unico formato pubblicato): lo apre ``bsdtar``
(libarchive), installato nell'immagine.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from shapely.geometry import Point

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import dataset_versions_repo
from limen.data.repos.landslide_events_repo import LandslideEvent, upsert_many
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

URL = "https://zenodo.org/api/records/13742643/files/RER2023_V1.rar/content"
FILE = "RER2023_V1.rar"
SORGENTE = "rer2023"
LICENZA = "CC BY 4.0, Berti et al. 2025 (ESSD), Regione Emilia-Romagna"
#: Da aumentare quando cambia come si leggono le righe.
VERSIONE_CALCOLO = 1
EVENTO = datetime(2023, 5, 16, 20, 0, tzinfo=ZoneInfo("Europe/Rome")).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Frana:
    x: float
    y: float
    classe: str | None


@dataclass(frozen=True, slots=True)
class Conti:
    frane: int
    celle: int
    fuori_griglia: int


async def risolvi_file() -> Path | None:
    """Il RAR locale (``LIMEN_RER2023_RAR``) o quello di Zenodo in cache."""
    esplicito = os.getenv("LIMEN_RER2023_RAR", "").strip()
    if esplicito:
        path = Path(esplicito).expanduser()
        if not path.is_file():
            log.error("rer2023.file_mancante", path=str(path))
            return None
        return path
    dest = Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser() / FILE
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    log.info("rer2023.download", url=URL, dest=str(dest))
    resp = await fetch_with_retry("GET", URL, client=await SharedHttpClient.get())
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def leggi(path: Path) -> tuple[list[Frana], int]:
    """I centroidi dei poligoni, nel sistema del file, e il suo codice EPSG."""
    import pyogrio  # gruppo geo: import locale come per gli altri vettori
    from shapely import from_wkb

    with tempfile.TemporaryDirectory() as cartella:
        subprocess.run(["bsdtar", "-xf", str(path), "-C", cartella], check=True)
        shp = next(Path(cartella).rglob("*.shp"))
        crs = pyogrio.read_info(shp)["crs"]
        meta, _, geometrie, campi = pyogrio.raw.read(shp)
    if not crs or not str(crs).upper().startswith("EPSG:"):
        raise ValueError(f"sistema di riferimento inatteso in {path.name}: {crs!r}")
    colonne = dict(zip(meta["fields"], campi, strict=True))
    classi = colonne.get("ClassNew")
    frane = []
    for i, wkb in enumerate(geometrie):
        if wkb is None:
            continue
        c = from_wkb(wkb).centroid
        classe = str(classi[i]) if classi is not None and classi[i] else None
        frane.append(Frana(x=float(c.x), y=float(c.y), classe=classe))
    return frane, int(str(crs).split(":")[1])


async def _celle(frane: list[Frana], srid: int) -> list[tuple[int, str, float, float]]:
    """``(indice, cella, lon, lat)`` delle frane che cadono in una cella di Limen.

    Una cella sola per frana, come per Marche-Umbria: le griglie di due
    regioni confinanti si sovrappongono sul confine.
    """
    async with acquire() as conn:
        righe = await conn.fetch(
            """
            WITH p AS (
                SELECT i, ST_Transform(ST_SetSRID(ST_MakePoint(x, y), $4), 4326) AS g
                FROM unnest($1::int[], $2::float8[], $3::float8[]) AS t(i, x, y)
            )
            SELECT DISTINCT ON (p.i) p.i, c.id, ST_X(p.g) AS lon, ST_Y(p.g) AS lat
            FROM p JOIN grid_cells c ON ST_Contains(c.geom, p.g)
            ORDER BY p.i, c.id
            """,
            list(range(len(frane))),
            [f.x for f in frane],
            [f.y for f in frane],
            srid,
        )
    return [(r["i"], r["id"], float(r["lon"]), float(r["lat"])) for r in righe]


def per_cella(
    frane: list[Frana], in_cella: list[tuple[int, str, float, float]]
) -> list[LandslideEvent]:
    """Un evento per cella: la prima frana che ci cade, col conto delle altre."""
    quante = Counter(cella for _, cella, _, _ in in_cella)
    eventi: dict[str, LandslideEvent] = {}
    for i, cella, lon, lat in in_cella:
        if cella in eventi:
            continue
        eventi[cella] = LandslideEvent(
            id=f"{SORGENTE}:{cella}",
            source=SORGENTE,
            event_time=EVENTO,
            geom=Point(lon, lat),
            temporal_accuracy="T3",
            geographic_accuracy="P1",
            landslide_type=frane[i].classe,
            attributes={
                "catalogue": SORGENTE,
                "numero_frane": quante[cella],
                "data": "convenzionale: alluvione del 16/05/2023, 20 locali (T3)",
            },
        )
    return list(eventi.values())


async def carica(path: Path, *, forzato: bool = False) -> Conti | None:
    """L'inventario in ``landslide_events``; ``None`` se è lo stesso della volta prima."""
    versione = dataset_versions_repo.content_hash(
        [f"v{VERSIONE_CALCOLO}".encode(), path.read_bytes()]
    )
    if not forzato and await dataset_versions_repo.find(SORGENTE, "landslide_events", versione):
        log.info("rer2023.invariato", version=versione[:12])
        return None
    frane, srid = leggi(path)
    in_cella = await _celle(frane, srid)
    eventi = per_cella(frane, in_cella)
    await upsert_many(eventi)
    conti = Conti(frane=len(frane), celle=len(eventi), fuori_griglia=len(frane) - len(in_cella))
    await dataset_versions_repo.record(
        source=SORGENTE,
        dataset="landslide_events",
        version=versione,
        metadata={"licence": LICENZA, **asdict(conti)},
    )
    log.info("rer2023.caricato", **asdict(conti))
    return conti
