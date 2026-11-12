"""FraneItalia v02 → ``landslide_events`` (#500): le frane datate dopo e-ITALICA.

e-ITALICA si ferma al 2021. FraneItalia (Calvello e Pecoraro, Università di
Salerno, Zenodo 10.5281/zenodo.15144334, CC BY 4.0) raccoglie dalla stampa
online le frane italiane dal 2010 al 2024, con il giorno e una classe di
accuratezza per luogo e data. Entra con ``source = 'franeitalia'``, così il
backtest può prenderla o lasciarla con ``LIMEN_BACKTEST_SORGENTI``.

Tre scelte, tutte dichiarate negli ``attributes`` della riga:

* **Precisione di luogo** sulla scala di ITALICA. Il catalogo non pubblica la
  legenda di ``Sd`` nei file; la si legge dai dati: ``A`` ha un indirizzo o una
  frazione (``P1``), ``C`` un luogo approssimato e ``M`` il solo comune
  (``P10``), ``AE`` è un evento areale su più comuni (``P100``). Nel dubbio la
  classe più larga: il backtest con ``PRECISIONE=P1`` deve poter contare su
  ciò che tiene.
* **Ora**: ``HH:MM`` è ``T1``, una parte del giorno (mattina, notte…) è ``T2``
  all'ora convenzionale di ``_PARTI_DEL_GIORNO``, nessuna ora è ``T3`` a
  mezzogiorno. Ore locali, salvate in UTC. Una data che il catalogo dichiara
  stimata resta ``T3`` con ``data_stimata``.
* **Doppioni**: fino al 2021 le stesse frane possono stare in e-ITALICA, che
  vince. Una riga di FraneItalia entro ``_DOPPIONE_KM`` e un giorno da un
  evento ITALICA non entra.

Le frane innescate da sisma, attività umana o «altro» restano fuori: il
truth set è di frane da pioggia, come ITALICA. «n.a.» entra, perché nella
stampa la causa spesso non è scritta.
"""

from __future__ import annotations

import math
import os
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from shapely.geometry import Point

from limen.core.logging import get_logger
from limen.data.repos import dataset_versions_repo
from limen.data.repos.landslide_events_repo import (
    LandslideEvent,
    eventi_del_catalogo,
    upsert_many,
)
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

URL = "https://zenodo.org/api/records/15144334/files/FraneItalia_ver02.gpkg/content"
FILE = "FraneItalia_ver02.gpkg"
SORGENTE = "franeitalia"
#: Da aumentare quando cambia come si leggono le righe: il file sarebbe lo
#: stesso, le righe scritte no.
VERSIONE_CALCOLO = 1

_ROMA = ZoneInfo("Europe/Rome")
_DOPPIONE_KM = 5.0
_PRECISIONE = {"A": "P1", "C": "P10", "M": "P10", "AE": "P100"}
_CAUSE_ESCLUSE = frozenset({"earthquake", "human activity", "other"})
_PARTI_DEL_GIORNO = {
    "midnight": 0,
    "night": 1,
    "late night": 4,
    "early morning": 6,
    "morning": 9,
    "late morning": 11,
    "midday": 12,
    "early afternoon": 13,
    "afternoon": 15,
    "late afternoon": 17,
    "early evening": 19,
    "evening": 20,
    "late evening": 22,
    "early night": 22,
}


@dataclass(frozen=True, slots=True)
class Conti:
    letti: int
    tenuti: int
    doppioni: int
    altre_cause: int
    illeggibili: int


async def risolvi_file() -> Path | None:
    """Il GeoPackage locale (``LIMEN_FRANEITALIA_GPKG``) o quello di Zenodo in cache."""
    esplicito = os.getenv("LIMEN_FRANEITALIA_GPKG", "").strip()
    if esplicito:
        path = Path(esplicito).expanduser()
        if not path.is_file():
            log.error("franeitalia.file_mancante", path=str(path))
            return None
        return path
    dest = Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser() / FILE
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    log.info("franeitalia.download", url=URL, dest=str(dest))
    resp = await fetch_with_retry("GET", URL, client=await SharedHttpClient.get())
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def _giorno(raw: str | None) -> date | None:
    try:
        return datetime.strptime((raw or "").strip(), "%d/%m/%y").date()
    except ValueError:
        return None


def istante(giorno: date, ora: str | None, certa: bool) -> tuple[datetime, str]:
    """L'istante dell'evento in UTC e la sua classe ITALICA (T1/T2/T3)."""
    testo = (ora or "").strip().lower()
    quando: time | None = None
    classe = "T3"
    if certa and testo:
        try:
            quando = datetime.strptime(testo, "%H:%M").time()
            classe = "T1"
        except ValueError:
            if testo in _PARTI_DEL_GIORNO:
                quando = time(_PARTI_DEL_GIORNO[testo])
                classe = "T2"
    locale = datetime.combine(giorno, quando or time(12), tzinfo=_ROMA)
    return locale.astimezone(UTC), classe


def _testo(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def leggi(path: Path) -> tuple[list[LandslideEvent], int, int]:
    """Le righe del GeoPackage come eventi; con quante scartate per causa e illeggibili."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        (tabella,) = con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
        ).fetchone()
        righe = con.execute(f'SELECT * FROM "{tabella}"').fetchall()
    finally:
        con.close()
    eventi: list[LandslideEvent] = []
    altre_cause = illeggibili = 0
    for r in righe:
        causa = (_testo(r["Trigger"]) or "n.a.").lower()
        if causa in _CAUSE_ESCLUSE:
            altre_cause += 1
            continue
        giorno = _giorno(r["Initial day"])
        lat, lon = r["LAT"], r["LONG"]
        if giorno is None or lat is None or lon is None or r["ID"] is None:
            illeggibili += 1
            continue
        certa = (_testo(r["Td"]) or "").lower() == "certain"
        quando, classe_ora = istante(giorno, r["Time"], certa)
        sd = (_testo(r["Sd"]) or "").upper()
        fine = _giorno(r["Final day"])
        eventi.append(
            LandslideEvent(
                id=f"{SORGENTE}:{r['ID']}",
                source=SORGENTE,
                event_time=quando,
                geom=Point(float(lon), float(lat)),
                temporal_accuracy=classe_ora,
                geographic_accuracy=_PRECISIONE.get(sd),
                landslide_type=_testo(r["Typology"]),
                region=_testo(r["Region"]),
                municipality=_testo(r["Municipality(-ies)"]),
                attributes={
                    "catalogue": SORGENTE,
                    "sd": sd or None,
                    "data_stimata": not certa,
                    "causa": causa,
                    "classe_conseguenze": _testo(r["Class"]),
                    "tipo_evento": _testo(r["Magnitude category"]),
                    "numero_frane": r["Number"],
                    "giorno_finale": fine.isoformat() if fine else None,
                    "luogo": _testo(r["Site(s)"]),
                },
            )
        )
    return eventi, altre_cause, illeggibili


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = math.radians(b[0] - a[0]) * math.cos(math.radians((a[1] + b[1]) / 2))
    return 6371.0 * math.hypot(dx, math.radians(b[1] - a[1]))


def togli_doppioni(
    eventi: list[LandslideEvent], italica: list[tuple[datetime, float, float]]
) -> tuple[list[LandslideEvent], int]:
    """Via le righe che e-ITALICA ha già: entro ``_DOPPIONE_KM`` e un giorno."""
    per_giorno: dict[date, list[tuple[float, float]]] = defaultdict(list)
    for quando, lon, lat in italica:
        per_giorno[quando.date()].append((lon, lat))
    tenuti: list[LandslideEvent] = []
    for e in eventi:
        c = e.geom.centroid
        p = (c.x, c.y)
        giorno = e.event_time.date()
        vicini = (q for d in (-1, 0, 1) for q in per_giorno.get(giorno + timedelta(days=d), ()))
        if not any(_km(p, q) <= _DOPPIONE_KM for q in vicini):
            tenuti.append(e)
    return tenuti, len(eventi) - len(tenuti)


async def carica(path: Path, *, forzato: bool = False) -> Conti | None:
    """Il GeoPackage in ``landslide_events``; ``None`` se è lo stesso della volta prima.

    Pool già aperto: va chiamato dopo ITALICA, che deve esserci per i doppioni.
    """
    versione = dataset_versions_repo.content_hash(
        [f"v{VERSIONE_CALCOLO}".encode(), path.read_bytes()]
    )
    if not forzato and await dataset_versions_repo.find(SORGENTE, "landslide_events", versione):
        log.info("franeitalia.invariato", version=versione[:12])
        return None
    eventi, altre_cause, illeggibili = leggi(path)
    if eventi:
        fine = max(e.event_time for e in eventi) + timedelta(days=2)
        italica = await eventi_del_catalogo("italica", fino_a=fine)
    else:
        italica = []
    tenuti, doppioni = togli_doppioni(eventi, italica)
    await upsert_many(tenuti)
    conti = Conti(
        letti=len(eventi) + altre_cause + illeggibili,
        tenuti=len(tenuti),
        doppioni=doppioni,
        altre_cause=altre_cause,
        illeggibili=illeggibili,
    )
    await dataset_versions_repo.record(
        source=SORGENTE,
        dataset="landslide_events",
        version=versione,
        metadata={"licence": "CC BY 4.0", **asdict(conti)},
    )
    log.info("franeitalia.caricato", **asdict(conti))
    return conti
