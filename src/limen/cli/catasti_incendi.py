"""``limen catasti-incendi`` — i catasti regionali degli incendi in ``catasti_incendi`` (#498).

La L. 353/2000 obbliga a censire le aree percorse dal fuoco. EFFIS mappa gli
incendi grandi; i catasti hanno anche quelli da un ettaro, e sono la verità
che manca al backtest incendio per gli incendi piccoli. Tre regioni li
pubblicano con il giorno dell'incendio e una licenza aperta (ricognizione
del 2026-11-12 nella #498):

* **Basilicata** — WFS RSDI ``aree_percorse_dal_fuoco:incendi``, 2004 a oggi,
  IODL 2.0;
* **Sardegna** — CFVA, uno zip per anno dal 2005, CC BY 4.0;
* **Emilia-Romagna** — catasto regionale 2003-2024, un solo shapefile, CC BY.

Ogni ente cambia nomi dei campi, formato della data e sistema di riferimento
da un anno all'altro (la Sardegna usa cinque nomi per la data e quattro
sistemi in vent'anni): la lettura cerca il campo fra i nomi noti e prende il
sistema dal file. Una riga per incendio: i poligoni con la stessa chiave
dell'ente sono uniti; dove l'ente non dà una chiave (Sardegna fino al 2013)
ogni poligono è un incendio.

Non entra nel punteggio: ``fire_perimeters`` (EFFIS) resta l'unica tabella
che lo sweep legge. Idempotente: un ente i cui file non sono cambiati non
riscrive niente (impronta in ``dataset_versions``).
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from limen.cli.bootstrap_static import FORCE_ENV
from limen.config.percorsi import radice_dati
from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import dataset_versions_repo
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

#: Da aumentare quando cambia come si leggono i file.
VERSIONE_CALCOLO = 1
DATASET = "catasti_incendi"

_CAMPI_DATA = ("data_inc", "data_incendio", "data_ince", "dt_ince", "data")
_CAMPI_CHIAVE = ("inc_id", "id_ince", "cod_incend", "incendio_id")
_FORMATI_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d")

_WFS_BASILICATA = (
    "https://rsdi.regione.basilicata.it/rbgeoserver2016/aree_percorse_dal_fuoco/ows"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeNames=aree_percorse_dal_fuoco:incendi"
    "&outputFormat=application/json&srsName=EPSG:4326"
)
_SARDEGNA = (
    "https://webgis.regione.sardegna.it/scaricocartografiaETL/cfva/areeIncendiatePerim{anno}.zip"
)
_EMILIA_ROMAGNA = (
    "https://mappegis.regione.emilia-romagna.it/moka/ckan/foreste/AreePercorseDalFuoco.zip"
)


@dataclass(frozen=True, slots=True)
class File:
    """Un file scaricato: il nome in cache e se resta valido per sempre."""

    nome: str
    url: str
    definitivo: bool


@dataclass(frozen=True, slots=True)
class Ente:
    fonte: str
    licenza: str
    attribuzione: str
    file: Callable[[int], list[File]]
    #: Un 404 su un file vuol dire «anno non ancora pubblicato», non un errore.
    tollera_assenti: bool = False


def _file_sardegna(anno_corrente: int) -> list[File]:
    return [
        File(f"sardegna_{a}.zip", _SARDEGNA.format(anno=a), definitivo=a < anno_corrente - 1)
        for a in range(2005, anno_corrente + 1)
    ]


ENTI: tuple[Ente, ...] = (
    Ente(
        fonte="catasto_basilicata",
        licenza="IODL 2.0",
        attribuzione="Regione Basilicata — RSDI, aree percorse dal fuoco",
        file=lambda _anno: [File("basilicata.geojson", _WFS_BASILICATA, definitivo=False)],
    ),
    Ente(
        fonte="catasto_sardegna",
        licenza="CC BY 4.0",
        attribuzione="Regione Autonoma della Sardegna — Corpo Forestale e di Vigilanza Ambientale",
        file=_file_sardegna,
        tollera_assenti=True,
    ),
    Ente(
        fonte="catasto_emilia_romagna",
        licenza="CC BY 4.0",
        attribuzione="Regione Emilia-Romagna — Catasto regionale delle aree percorse dal fuoco",
        file=lambda _anno: [File("emilia_romagna.zip", _EMILIA_ROMAGNA, definitivo=False)],
    ),
)


@dataclass(frozen=True, slots=True)
class Poligono:
    chiave: str
    giorno: date
    wkb: bytes
    srid: int


def cartella() -> Path:
    return radice_dati() / "catasti_incendi"


def leggi_data(valore: Any) -> date | None:
    """Il giorno dell'incendio da un campo che ogni ente scrive a modo suo."""
    if valore is None:
        return None
    testo = str(valore).strip().rstrip("Z")[:10]
    if not testo or testo in {"NaT", "None", "nan"}:
        return None
    for formato in _FORMATI_DATA:
        try:
            return datetime.strptime(testo, formato).date()
        except ValueError:
            continue
    return None


def _campo(campi: Sequence[str], nomi: Sequence[str]) -> str | None:
    minuscoli = {c.lower(): c for c in campi}
    return next((minuscoli[n] for n in nomi if n in minuscoli), None)


def _srid(crs: str | None, sorgente: str) -> int:
    if not crs or not crs.upper().startswith("EPSG:"):
        raise ValueError(f"{sorgente}: sistema di riferimento non riconosciuto ({crs!r})")
    return int(crs.split(":", 1)[1])


def _vettori(path: Path) -> list[str]:
    """I percorsi GDAL dei vettori in un file: lo shapefile o il GeoJSON dentro lo zip."""
    if path.suffix != ".zip":
        return [str(path.resolve())]
    with zipfile.ZipFile(path) as archivio:
        nomi = [n for n in archivio.namelist() if n.lower().endswith((".shp", ".geojson"))]
    return [f"/vsizip/{path.resolve()}/{n}" for n in nomi]


def leggi(path: Path) -> tuple[list[Poligono], int]:
    """I poligoni datati di un file e quanti ne sono rimasti fuori senza data."""
    import pyogrio  # gruppo geo: import locale come per gli altri vettori

    poligoni: list[Poligono] = []
    senza_data = 0
    for vettore in _vettori(path):
        meta, _, geometrie, valori = pyogrio.raw.read(vettore)
        campi = list(meta["fields"])
        nome_data = _campo(campi, _CAMPI_DATA)
        if nome_data is None:
            raise ValueError(f"{vettore}: nessun campo data fra {campi}")
        colonne = dict(zip(campi, valori, strict=True))
        nome_chiave = _campo(campi, _CAMPI_CHIAVE)
        srid = _srid(meta["crs"], vettore)
        for i, wkb in enumerate(geometrie):
            if wkb is None:
                continue
            giorno = leggi_data(colonne[nome_data][i])
            if giorno is None:
                senza_data += 1
                continue
            chiave = str(colonne[nome_chiave][i]).strip() if nome_chiave else ""
            if not chiave or chiave in {"None", "nan", "0"}:
                chiave = f"{path.stem}:{i}"
            poligoni.append(Poligono(chiave=chiave, giorno=giorno, wkb=bytes(wkb), srid=srid))
    return poligoni, senza_data


async def scarica(ente: Ente, oggi: date) -> list[Path]:
    """I file dell'ente in cache; quelli di anni chiusi non si riscaricano."""
    dest = cartella()
    dest.mkdir(parents=True, exist_ok=True)
    client = await SharedHttpClient.get()
    percorsi: list[Path] = []
    for f in ente.file(oggi.year):
        path = dest / f.nome
        if f.definitivo and path.is_file() and path.stat().st_size > 0:
            percorsi.append(path)
            continue
        try:
            resp = await fetch_with_retry("GET", f.url, client=client)
        except httpx.HTTPStatusError as exc:
            if ente.tollera_assenti and exc.response.status_code == 404:
                log.info("catasti_incendi.assente", fonte=ente.fonte, url=f.url)
                continue
            raise
        path.write_bytes(resp.content)
        percorsi.append(path)
    return percorsi


async def _scrivi(ente: Ente, poligoni: list[Poligono], versione_id: int) -> int:
    """Una riga per incendio, i poligoni uniti e riportati in EPSG:4326."""
    async with acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM catasti_incendi WHERE fonte = $1", ente.fonte)
        stato = await conn.execute(
            """
            WITH p AS (
                SELECT k, d,
                       ST_MakeValid(ST_Transform(ST_SetSRID(ST_GeomFromWKB(w), s), 4326)) AS g
                FROM unnest($2::text[], $3::date[], $4::bytea[], $5::int[]) AS t(k, d, w, s)
            ),
            u AS (
                SELECT k, min(d) AS d,
                       ST_Multi(ST_CollectionExtract(ST_Union(g), 3)) AS g
                FROM p GROUP BY k
            )
            INSERT INTO catasti_incendi
                (id, fonte, fire_date, area_ha, geom, dataset_version_id, attributes)
            SELECT $1 || ':' || k, $1, d,
                   ST_Area(ST_Transform(g, 3035)) / 10000.0, g, $6,
                   jsonb_build_object('chiave', k, 'licenza', $7::text)
            FROM u WHERE NOT ST_IsEmpty(g)
            """,
            ente.fonte,
            [p.chiave for p in poligoni],
            [p.giorno for p in poligoni],
            [p.wkb for p in poligoni],
            [p.srid for p in poligoni],
            versione_id,
            ente.licenza,
        )
    return int(stato.split()[-1])


async def carica(ente: Ente, *, forzato: bool, oggi: date) -> dict[str, int] | None:
    """Un ente in ``catasti_incendi``; ``None`` se i file sono quelli della volta prima."""
    percorsi = await scarica(ente, oggi)
    if not percorsi:
        raise RuntimeError(f"{ente.fonte}: nessun file scaricato")
    versione = dataset_versions_repo.content_hash(
        [f"v{VERSIONE_CALCOLO}".encode(), *(p.read_bytes() for p in percorsi)]
    )
    if not forzato and await dataset_versions_repo.find(ente.fonte, DATASET, versione):
        log.info("catasti_incendi.invariato", fonte=ente.fonte, version=versione[:12])
        return None
    poligoni: list[Poligono] = []
    senza_data = 0
    for path in percorsi:
        letti, scartati = leggi(path)
        poligoni += letti
        senza_data += scartati
    versione_id = await dataset_versions_repo.record(
        source=ente.fonte,
        dataset=DATASET,
        version=versione,
        metadata={
            "licence": ente.licenza,
            "attribution": ente.attribuzione,
            "files": [p.name for p in percorsi],
        },
    )
    incendi = await _scrivi(ente, poligoni, versione_id)
    conti = {"poligoni": len(poligoni), "senza_data": senza_data, "incendi": incendi}
    log.info("catasti_incendi.caricato", fonte=ente.fonte, **conti)
    return conti


async def sincronizza(*, forzato: bool) -> dict[str, int]:
    """Ogni ente; uno che non risponde non ferma gli altri."""
    oggi = datetime.now(UTC).date()
    falliti = 0
    for ente in ENTI:
        try:
            await carica(ente, forzato=forzato, oggi=oggi)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            falliti += 1
            log.error("catasti_incendi.fallito", fonte=ente.fonte, error=str(exc))
    return {"enti": len(ENTI), "falliti": falliti}


async def run() -> int:
    forzato = os.environ.get(FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}
    try:
        async with lifespan_pool():
            await run_migrations()
            conti = await sincronizza(forzato=forzato)
    finally:
        await SharedHttpClient.aclose()
    log.info("catasti_incendi.done", **conti)
    return 1 if conti["falliti"] else 0


__all__ = ["ENTI", "leggi", "leggi_data", "run", "sincronizza"]
