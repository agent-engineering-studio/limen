"""Pioggia oraria misurata dai pluviometri di Meteotrentino, per nodo.

La stessa domanda dei pluviometri ARPA Lombardia (#505), sul Trentino: quanto
del mancato è della pioggia del modello e quanto del motore. Archivio aperto
della Provincia autonoma di Trento (CC BY 4.0, «Provincia Autonoma di Trento -
Meteotrentino»): l'anagrafica in ``catalog/stations.json`` e, per ogni mese, un
Parquet con tutte le stazioni e le variabili (``station, code, time, value,
quality``), elencato in ``bulk/manifest.json``. I Parquet si leggono con
``pyarrow``: gruppo uv ``pluviometri``.

Il file di dicembre porta anche il pomeriggio del 31 dicembre dell'anno prima,
che sta già nel dicembre precedente (``2026-12`` ripete 3.580 righe di
``2025-12``): da ogni file si tengono solo le righe del suo mese, o lo stesso
istante si conterebbe due volte.

La pioggia (codice ``10.00``) è il totale dei cinque minuti che finiscono
all'istante indicato. I timestamp del Parquet sono assoluti; l'ora solare
(UTC+1) serve a dire a che giorno e a che mese appartiene una misura.

Contano i codici di qualità validi (1-3) e il 145, il teletrasmesso non ancora
validato: la validazione arriva con più di un anno di ritardo (a novembre 2026
ottobre 2025 era al 79 % di 145), e senza il 145 un backtest recente non
avrebbe pioggia. Il log dice quante misure lo sono. Restano fuori i dati dubbi
(140), la neve (85, 90) e le serie ricostruite con l'intelligenza artificiale,
che sono stime e non misure.

Un'ora è misurata se ha tutte le sue dodici misure **e** il suo giorno ne ha
almeno ``_COPERTURA_MINIMA``; altrimenti è ``None`` e resta sul modello. L'ora
da sola non basta: prima del 2009 l'archivio salvava solo gli intervalli
piovosi, e un'ora di pioggia continua sembrerebbe completa in un giorno di
buchi. Il giorno da solo nemmeno: le righe che mancano (un picco marcato
dubbio, una trasmissione caduta) cadono proprio nelle ore di temporale, che
varrebbero zero.

Ogni file si riduce subito a somme e conteggi per stazione e ora: le righe a
cinque minuti di anni di backtest non stanno in memoria.

Sola lettura: una sorgente che non risponde restituisce ``{}`` e logga
``integration.degraded``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import httpx

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry
from limen.integrations.arpa_lombardia.pluviometri import Pluviometro, associa

log = get_logger(__name__)

BASE = "https://archivio.meteotrentino.it/share"
STAZIONI = "catalog/stations.json"
MANIFEST = "bulk/manifest.json"
#: Precipitazione, totale dei cinque minuti.
CODICE = "10.00"
_VALIDATI = (1, 2, 3)
_TELETRASMESSO = 145
_PASSO = timedelta(minutes=5)
_MISURE_ORA = timedelta(hours=1) // _PASSO
_CET = timezone(timedelta(hours=1))
_COPERTURA_MINIMA = 0.9


@dataclass(frozen=True, slots=True)
class OraStazione:
    """Le misure accettate di una stazione nell'ora UTC ``(ora-1h, ora]``."""

    stazione: str
    ora: datetime
    misure: int
    mm: float
    teletrasmesse: int


def _giorno(istante: datetime) -> date:
    """Il giorno solare dell'intervallo che finisce in ``istante``."""
    return (istante.astimezone(_CET) - timedelta(minutes=1)).date()


def _mese(anno: int, mese: int) -> tuple[datetime, datetime]:
    """Primo istante del mese e del successivo, in ora solare."""
    dopo = (anno + 1, 1) if mese == 12 else (anno, mese + 1)
    return datetime(anno, mese, 1, tzinfo=_CET), datetime(*dopo, 1, tzinfo=_CET)


def file_per(
    manifest: dict[str, Any], start: datetime, end: datetime
) -> list[tuple[str, datetime, datetime]]:
    """``(file, inizio, fine del mese)`` dei mesi che toccano ``(start, end]``."""
    out = []
    for percorso, voce in manifest.items():
        da, a = _mese(int(voce["year"]), int(voce["month"]))
        if da <= end and a > start:
            out.append((percorso, da, a))
    return sorted(out, key=lambda f: f[1])


def ore_del_file(
    contenuto: bytes,
    sensori: list[str],
    *,
    da: datetime,
    a: datetime,
) -> list[OraStazione]:
    """Le ore di pioggia accettata di ``sensori`` con istanti in ``[da, a)``."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    tabella = pq.read_table(
        pa.BufferReader(contenuto),
        columns=["station", "time", "value", "quality"],
        filters=[
            ("code", "=", CODICE),
            ("station", "in", sensori),
            ("quality", "in", [*_VALIDATI, _TELETRASMESSO]),
        ],
    )
    tempo = tabella["time"]
    dentro = pc.and_(
        pc.greater_equal(tempo, pa.scalar(da, type=tempo.type)),
        pc.less(tempo, pa.scalar(a, type=tempo.type)),
    )
    tabella = tabella.filter(dentro)
    tabella = tabella.append_column(
        "ora", pc.ceil_temporal(tabella["time"], unit="hour")
    ).append_column(
        "teletrasmessa", pc.cast(pc.equal(tabella["quality"], _TELETRASMESSO), pa.int64())
    )
    ore = tabella.group_by(["station", "ora"]).aggregate(
        [("value", "count"), ("value", "sum"), ("teletrasmessa", "sum")]
    )
    return [
        OraStazione(stazione=s, ora=o.astimezone(UTC), misure=n, mm=mm, teletrasmesse=t)
        for s, o, n, mm, t in zip(
            ore["station"].to_pylist(),
            ore["ora"].to_pylist(),
            ore["value_count"].to_pylist(),
            ore["value_sum"].to_pylist(),
            ore["teletrasmessa_sum"].to_pylist(),
            strict=True,
        )
    ]


def ore_dai_cinque_minuti(
    ore: Iterable[OraStazione],
    *,
    sensori: list[str],
    start: datetime,
    end: datetime,
) -> dict[datetime, list[float | None]]:
    """Ore UTC ``(h-1, h]`` in ``(start, end]`` → mm per sensore (nell'ordine di ``sensori``)."""
    inizio_cet, fine_cet = start.astimezone(_CET), end.astimezone(_CET)

    def attese(giorno: date) -> float:
        # Le misure di quel giorno dentro la finestra: ai due capi è un giorno a metà.
        da = max(datetime.combine(giorno, datetime.min.time(), tzinfo=_CET), inizio_cet)
        a = min(
            datetime.combine(giorno + timedelta(days=1), datetime.min.time(), tzinfo=_CET), fine_cet
        )
        return max((a - da) / _PASSO, 1.0)

    per_ora: dict[tuple[str, datetime], tuple[int, float]] = {}
    per_giorno: dict[tuple[str, date], int] = defaultdict(int)
    for o in ore:
        if not start < o.ora <= end:
            continue
        n, mm = per_ora.get((o.stazione, o.ora), (0, 0.0))
        per_ora[(o.stazione, o.ora)] = (n + o.misure, mm + o.mm)
        per_giorno[(o.stazione, _giorno(o.ora))] += o.misure

    def valore(s: str, ora: datetime) -> float | None:
        n, mm = per_ora.get((s, ora), (0, 0.0))
        giorno = _giorno(ora)
        if n < _MISURE_ORA or per_giorno[(s, giorno)] < _COPERTURA_MINIMA * attese(giorno):
            return None
        return round(mm, 2)

    out: dict[datetime, list[float | None]] = {}
    ora = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while ora <= end:
        out[ora] = [valore(s, ora) for s in sensori]
        ora += timedelta(hours=1)
    return out


async def _scarica(percorso: str) -> httpx.Response:
    client = await SharedHttpClient.get()
    return await fetch_with_retry("GET", f"{BASE}/{percorso}", client=client)


async def pluviometri(bbox: tuple[float, float, float, float]) -> list[Pluviometro]:
    """Le stazioni con pioggia a cinque minuti dentro ``bbox`` (lon/lat), dismesse comprese."""
    min_lon, min_lat, max_lon, max_lat = bbox
    try:
        stazioni = (await _scarica(STAZIONI)).json()["features"]
        tutte = [
            Pluviometro(
                idsensore=str(f["properties"]["code"]),
                nome=str(f["properties"].get("name", "")),
                lon=float(f["geometry"]["coordinates"][0]),
                lat=float(f["geometry"]["coordinates"][1]),
                dal=datetime.fromisoformat(f["properties"]["first"]).date(),
                al=datetime.fromisoformat(f["properties"]["last"]).date(),
            )
            for f in stazioni
            if CODICE in f["properties"].get("codes", [])
        ]
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        log.warning("integration.degraded", source="meteotrentino", error=str(exc))
        return []
    return [p for p in tutte if min_lon <= p.lon <= max_lon and min_lat <= p.lat <= max_lat]


async def oraria(
    nodi: list[tuple[float, float]],
    start: datetime,
    end: datetime,
    *,
    raggio_km: float,
    bbox: tuple[float, float, float, float],
) -> dict[datetime, list[float | None]]:
    """Pioggia di ogni ora ``(h-1, h]`` in ``(start, end]``, per nodo (mm).

    Stessa forma di :func:`limen.integrations.arpa_lombardia.pluviometri.oraria`:
    ``None`` dove il nodo non ha un pluviometro entro ``raggio_km`` o il
    pluviometro in quell'ora non ha misurato.
    """
    attivi = [
        p
        for p in await pluviometri(bbox)
        if (p.dal is None or p.dal <= end.date()) and (p.al is None or p.al >= start.date())
    ]
    scelti = associa(nodi, attivi, raggio_km=raggio_km)
    sensori = sorted({p.idsensore for p in scelti if p is not None})
    if not sensori:
        return {}
    ore: list[OraStazione] = []
    try:
        mesi = file_per((await _scarica(MANIFEST)).json()["files"], start, end)
        for percorso, da, a in mesi:
            ore.extend(ore_del_file((await _scarica(percorso)).content, sensori, da=da, a=a))
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.warning("integration.degraded", source="meteotrentino", error=str(exc))
        return {}
    per_sensore = ore_dai_cinque_minuti(ore, sensori=sensori, start=start, end=end)
    indice = {s: k for k, s in enumerate(sensori)}
    misure = sum(o.misure for o in ore)
    log.info(
        "meteotrentino.oraria",
        nodi=len(nodi),
        nodi_con_pluviometro=sum(p is not None for p in scelti),
        sensori=len(sensori),
        file=len(mesi),
        misure=misure,
        quota_teletrasmesse=round(sum(o.teletrasmesse for o in ore) / misure, 3) if misure else 0.0,
    )
    return {
        ora: [None if p is None else valori[indice[p.idsensore]] for p in scelti]
        for ora, valori in per_sensore.items()
    }
