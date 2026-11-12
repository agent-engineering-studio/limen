"""Inventario Marche-Umbria 15/09/2022 → ``landslide_events`` (#500).

Le 1.687 frane innescate dal nubifragio del 15 settembre 2022 fra Cantiano,
Arcevia e Cagli, mappate sul terreno e da foto aeree a 1:15.000 (Santangelo
et al., *Scientific Data* 2023, CNR-IRPI; figshare 10.6084/m9.figshare.21981842,
CC BY 4.0). Entra con ``source = 'marche_umbria_2022'``, così il backtest può
prenderlo o lasciarlo con ``LIMEN_BACKTEST_SORGENTI``.

Tre scelte, dichiarate negli ``attributes``:

* **Una riga per cella**: il backtest conta celle-giorno, e 1.687 righe di
  un solo pomeriggio peserebbero nei conteggi più di un anno di ITALICA. Si
  tiene il punto (o il centroide del poligono) della prima frana di ogni
  cella, con ``numero_frane`` della cella.
* **Data**: ``Date`` nel file è il giorno del rilievo (dal 22/09 al 20/10),
  non della frana. L'innesco è il nubifragio del 15/09, piogge forti dal
  pomeriggio alla notte: ora convenzionale alle 20 locali, classe ``T2``.
* **Luogo** ``P1``: geometrie mappate, entro la cella.

Le geometrie fuori dalle celle di Limen non entrano: senza cella non c'è
niente da confrontare.
"""

from __future__ import annotations

import os
import zipfile
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

URL = "https://ndownloader.figshare.com/files/39121838"
FILE = "marche_umbria_2022_ELIM_DB.zip"
SORGENTE = "marche_umbria_2022"
LICENZA = "CC BY 4.0, Santangelo et al. 2023 (CNR-IRPI)"
#: Da aumentare quando cambia come si leggono le righe.
VERSIONE_CALCOLO = 1
EVENTO = datetime(2022, 9, 15, 20, 0, tzinfo=ZoneInfo("Europe/Rome")).astimezone(UTC)
_STRATI = ("ELIM_point", "ELIM_polygon")
_EPSG = 32633


@dataclass(frozen=True, slots=True)
class Frana:
    x: float
    y: float
    tipo: str | None
    zona: str | None


@dataclass(frozen=True, slots=True)
class Conti:
    frane: int
    celle: int
    fuori_griglia: int


async def risolvi_file() -> Path | None:
    """Lo zip locale (``LIMEN_MARCHE_UMBRIA_ZIP``) o quello di figshare in cache."""
    esplicito = os.getenv("LIMEN_MARCHE_UMBRIA_ZIP", "").strip()
    if esplicito:
        path = Path(esplicito).expanduser()
        if not path.is_file():
            log.error("marche_umbria.file_mancante", path=str(path))
            return None
        return path
    dest = Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser() / FILE
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    log.info("marche_umbria.download", url=URL, dest=str(dest))
    resp = await fetch_with_retry("GET", URL, client=await SharedHttpClient.get())
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def leggi(path: Path) -> list[Frana]:
    """Punti e centroidi dei poligoni, in EPSG:32633 come nel file."""
    import pyogrio  # gruppo geo: import locale come per gli altri vettori
    from shapely import from_wkb

    frane: list[Frana] = []
    with zipfile.ZipFile(path) as archivio:
        nomi = archivio.namelist()
    for strato in _STRATI:
        shp = next(n for n in nomi if n.endswith(f"{strato}.shp"))
        meta, _, geometrie, campi = pyogrio.raw.read(f"/vsizip/{path.resolve()}/{shp}")
        colonne = dict(zip(meta["fields"], campi, strict=True))
        for i, wkb in enumerate(geometrie):
            if wkb is None:
                continue
            c = from_wkb(wkb).centroid
            frane.append(
                Frana(
                    x=float(c.x),
                    y=float(c.y),
                    tipo=str(colonne["Descriptio"][i]) or None,
                    zona=str(colonne["Zone"][i]) or None,
                )
            )
    return frane


async def _celle(frane: list[Frana]) -> list[tuple[int, str, float, float]]:
    """``(indice, cella, lon, lat)`` delle frane che cadono in una cella di Limen.

    Una cella sola per frana: le griglie di due regioni confinanti si
    sovrappongono sul confine (1.791 incroci per 1.687 frane fra Marche e
    Umbria). Il backtest rilegge il punto con le celle della sua AOI.
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
            _EPSG,
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
        frana = frane[i]
        eventi[cella] = LandslideEvent(
            id=f"{SORGENTE}:{cella}",
            source=SORGENTE,
            event_time=EVENTO,
            geom=Point(lon, lat),
            temporal_accuracy="T2",
            geographic_accuracy="P1",
            landslide_type=frana.tipo,
            attributes={
                "catalogue": SORGENTE,
                "numero_frane": quante[cella],
                "zona": frana.zona,
                "data": "convenzionale: nubifragio del 15/09/2022, 20 locali",
            },
        )
    return list(eventi.values())


async def carica(path: Path, *, forzato: bool = False) -> Conti | None:
    """L'inventario in ``landslide_events``; ``None`` se è lo stesso della volta prima."""
    versione = dataset_versions_repo.content_hash(
        [f"v{VERSIONE_CALCOLO}".encode(), path.read_bytes()]
    )
    if not forzato and await dataset_versions_repo.find(SORGENTE, "landslide_events", versione):
        log.info("marche_umbria.invariato", version=versione[:12])
        return None
    frane = leggi(path)
    in_cella = await _celle(frane)
    eventi = per_cella(frane, in_cella)
    await upsert_many(eventi)
    conti = Conti(frane=len(frane), celle=len(eventi), fuori_griglia=len(frane) - len(in_cella))
    await dataset_versions_repo.record(
        source=SORGENTE,
        dataset="landslide_events",
        version=versione,
        metadata={"licence": LICENZA, **asdict(conti)},
    )
    log.info("marche_umbria.caricato", **asdict(conti))
    return conti
