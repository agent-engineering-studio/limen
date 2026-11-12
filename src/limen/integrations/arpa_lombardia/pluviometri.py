"""Pioggia oraria misurata dai pluviometri ARPA Lombardia, per nodo (#505).

Il backtest frane gira sulla pioggia di un modello a ~9 km; questa è la
pioggia caduta nel pluviometro, per chiedersi quanto del mancato è del modello
e quanto del motore. Open data di Regione Lombardia (Socrata, CC0): anagrafica
``nf78-nj6b``, misure a 10 minuti in tre dataset per periodo.

Le misure sono in **ora solare** (CET, UTC+1 tutto l'anno) e ogni valore è la
pioggia dei dieci minuti che finiscono all'ora indicata: un'ora ``(h-1, h]``
in UTC somma le righe con etichetta CET in ``(h, h+1]``.

Il portale non aggrega per ora (``date_trunc_ymdh`` non esiste in questa SoQL)
e un mese di dieci minuti su 250 sensori sono un milione di righe. Si chiedono
quindi due cose: le sole righe con pioggia, e il numero di righe valide per
sensore e giorno. Un giorno con almeno ``_COPERTURA_MINIMA`` delle sue misure
(144, meno ai capi della finestra) è misurato, e le sue ore senza righe di
pioggia valgono zero; un giorno con meno è ``None`` — un pluviometro fermo
non è un'ora asciutta.

Sola lettura: una sorgente che non risponde restituisce ``{}`` e logga
``integration.degraded``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import httpx

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

BASE = "https://www.dati.lombardia.it/resource"
ANAGRAFICA = "nf78-nj6b"
#: Le misure a 10 minuti: dataset e primo anno che copre.
DATASET = (("e7r2-7m84", 1900), ("2kar-pnuk", 2011), ("pstb-pga6", 2021))
_CET = timezone(timedelta(hours=1))
_PAGINA = 50_000
_STATI_VALIDI = "('VA','VV')"
_COPERTURA_MINIMA = 0.9


@dataclass(frozen=True, slots=True)
class Pluviometro:
    idsensore: str
    nome: str
    lon: float
    lat: float
    dal: date | None
    al: date | None


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = math.radians(b[0] - a[0]) * math.cos(math.radians((a[1] + b[1]) / 2))
    return 6371.0 * math.hypot(dx, math.radians(b[1] - a[1]))


def _giorno(raw: Any) -> date | None:
    return datetime.fromisoformat(str(raw)).date() if raw else None


def _cet(raw: str) -> datetime:
    return datetime.fromisoformat(raw).replace(tzinfo=_CET)


def _soql(t: datetime) -> str:
    return t.astimezone(_CET).replace(tzinfo=None).isoformat(timespec="seconds")


def dataset_per(start: datetime, end: datetime) -> list[str]:
    """I dataset delle misure che coprono ``[start, end]``."""
    anni = range(start.year, end.year + 1)
    fuori = [*(primo for _, primo in DATASET[1:]), 10_000]
    return [
        ds
        for (ds, primo), oltre in zip(DATASET, fuori, strict=True)
        if any(primo <= a < oltre for a in anni)
    ]


def associa(
    nodi: list[tuple[float, float]], pluviometri: list[Pluviometro], *, raggio_km: float
) -> list[Pluviometro | None]:
    """A ogni nodo il pluviometro più vicino entro ``raggio_km``, o nessuno."""
    out: list[Pluviometro | None] = []
    for n in nodi:
        vicino = min(pluviometri, key=lambda p: _km(n, (p.lon, p.lat)), default=None)
        out.append(vicino if vicino and _km(n, (vicino.lon, vicino.lat)) <= raggio_km else None)
    return out


def ore_dai_dieci_minuti(
    pioggia: list[tuple[str, str, float]],
    conteggi: list[tuple[str, date, int]],
    *,
    sensori: list[str],
    start: datetime,
    end: datetime,
) -> dict[datetime, list[float | None]]:
    """Ore UTC ``(h-1, h]`` in ``(start, end]`` → mm per sensore (nell'ordine di ``sensori``).

    ``pioggia``: ``(idsensore, data CET, mm)`` delle sole righe con pioggia;
    ``conteggi``: ``(idsensore, giorno CET, righe valide)``.
    """
    inizio_cet, fine_cet = start.astimezone(_CET), end.astimezone(_CET)

    def attese(giorno: date) -> float:
        # Le misure di quel giorno dentro la finestra: ai due capi è un giorno a metà.
        da = max(datetime.combine(giorno, datetime.min.time(), tzinfo=_CET), inizio_cet)
        a = min(
            datetime.combine(giorno + timedelta(days=1), datetime.min.time(), tzinfo=_CET), fine_cet
        )
        return max((a - da).total_seconds() / 600, 1.0)

    misurato = {(s, g) for s, g, n in conteggi if n >= _COPERTURA_MINIMA * attese(g)}
    somme: dict[tuple[str, datetime], float] = defaultdict(float)
    for s, raw, mm in pioggia:
        utc = _cet(raw).astimezone(UTC)
        ora = utc.replace(minute=0, second=0, microsecond=0)
        if ora < utc:
            ora += timedelta(hours=1)
        somme[(s, ora)] += mm
    out: dict[datetime, list[float | None]] = {}
    ora = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while ora <= end:
        # Il giorno CET dell'ultima misura dell'ora: (h+1) CET meno un istante.
        giorno = (ora.astimezone(_CET) - timedelta(minutes=1)).date()
        out[ora] = [
            round(somme.get((s, ora), 0.0), 2) if (s, giorno) in misurato else None for s in sensori
        ]
        ora += timedelta(hours=1)
    return out


async def _pagine(dataset: str, params: dict[str, str]) -> list[dict[str, Any]]:
    client = await SharedHttpClient.get()
    righe: list[dict[str, Any]] = []
    offset = 0
    while True:
        resp = await fetch_with_retry(
            "GET",
            f"{BASE}/{dataset}.json",
            client=client,
            params={**params, "$limit": str(_PAGINA), "$offset": str(offset)},
        )
        pagina: list[dict[str, Any]] = resp.json()
        righe.extend(pagina)
        if len(pagina) < _PAGINA:
            return righe
        offset += _PAGINA


async def pluviometri(bbox: tuple[float, float, float, float]) -> list[Pluviometro]:
    """I pluviometri dell'anagrafica dentro ``bbox`` (lon/lat), storici compresi."""
    min_lon, min_lat, max_lon, max_lat = bbox
    try:
        # lng/lat sono testo nel dataset: il filtro sul riquadro si fa qui.
        righe = await _pagine(ANAGRAFICA, {"tipologia": "Precipitazione"})
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("integration.degraded", source="arpa_lombardia", error=str(exc))
        return []
    tutti = [
        Pluviometro(
            idsensore=str(r["idsensore"]),
            nome=str(r.get("nomestazione", "")),
            lon=float(r["lng"]),
            lat=float(r["lat"]),
            dal=_giorno(r.get("datastart")),
            al=_giorno(r.get("datastop")),
        )
        for r in righe
        if r.get("lng") and r.get("lat")
    ]
    return [p for p in tutti if min_lon <= p.lon <= max_lon and min_lat <= p.lat <= max_lat]


async def oraria(
    nodi: list[tuple[float, float]],
    start: datetime,
    end: datetime,
    *,
    raggio_km: float,
    bbox: tuple[float, float, float, float],
) -> dict[datetime, list[float | None]]:
    """Pioggia di ogni ora ``(h-1, h]`` in ``(start, end]``, per nodo (mm).

    Stessa forma di :meth:`MergingArchive.oraria`, così il backtest la passa a
    ``pioggia_dal_radar``: ``None`` dove il nodo non ha un pluviometro entro
    ``raggio_km`` o il pluviometro quel giorno non ha misurato.
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
    elenco = ",".join(f"'{s}'" for s in sensori)
    # In CET: l'ora UTC (h-1, h] ha le etichette (h, h+1].
    finestra = f"data between '{_soql(start)}' and '{_soql(end)}'"
    filtro = f"idsensore in ({elenco}) AND {finestra} AND stato in {_STATI_VALIDI}"
    pioggia: list[tuple[str, str, float]] = []
    conteggi: list[tuple[str, date, int]] = []
    try:
        for ds in dataset_per(start, end):
            for r in await _pagine(ds, {"$where": f"{filtro} AND valore > 0", "$order": "data"}):
                pioggia.append((str(r["idsensore"]), str(r["data"]), float(r["valore"])))
            for r in await _pagine(
                ds,
                {
                    "$select": "idsensore, date_trunc_ymd(data) as giorno, count(*) as n",
                    "$where": f"{filtro} AND valore >= 0",
                    "$group": "idsensore, giorno",
                },
            ):
                giorno = _giorno(r["giorno"])
                if giorno is not None:
                    conteggi.append((str(r["idsensore"]), giorno, int(r["n"])))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("integration.degraded", source="arpa_lombardia", error=str(exc))
        return {}
    per_sensore = ore_dai_dieci_minuti(pioggia, conteggi, sensori=sensori, start=start, end=end)
    indice = {s: k for k, s in enumerate(sensori)}
    log.info(
        "arpa_lombardia.oraria",
        nodi=len(nodi),
        nodi_con_pluviometro=sum(p is not None for p in scelti),
        sensori=len(sensori),
        righe_pioggia=len(pioggia),
    )
    return {
        ora: [None if p is None else valori[indice[p.idsensore]] for p in scelti]
        for ora, valori in per_sensore.items()
    }
