"""Riempie la portata ordinaria per nodo GloFAS, un po' alla volta (#200).

Il riferimento costa due anni di archivio per nodo e l'API pubblica pesa le
richieste lunghe: calcolarlo in blocco dentro lo sweep esauriva il tetto
giornaliero in diciotto minuti. Qui lo si calcola fuori dallo sweep, entro
un budget di ``chiamate``, e ci si ferma al primo 429: il resto lo fa la notte
dopo.

**Il peso è per nodo, non per richiesta.** Open-Meteo conta una chiamata ogni
due settimane di dati per località: due anni sono ~52 chiamate a nodo, e un
lotto di 100 nodi (~5.200) sfora da solo il limite orario di 5.000 — è il 429
delle 00:18 dell'11 ottobre. Per questo i lotti sono piccoli e distanziati di
un minuto: il limite più stretto è quello al minuto, 600.

Un lotto fallito non si salva. ``fetch_grid`` restituisce un dizionario vuoto
per ogni punto di un lotto fallito, ed è diverso da una risposta con la serie
vuota: solo la seconda vuol dire «qui non c'è un fiume da misurare».
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from limen.core.logging import get_logger
from limen.data.repos import glofas_repo
from limen.integrations.openmeteo.flood import (
    DEFAULT_REFERENCE_PERCENTILE,
    DEFAULT_REFERENCE_WINDOW_DAYS,
    FLOOD_URL,
    MIN_REFERENCE_DAYS,
    NODE_SPACING_DEG,
    OpenMeteoFloodClient,
    _floats,
    _in_pausa,
    percentile_of,
)

log = get_logger(__name__)

#: Il limite al minuto dell'API pubblica è 600 chiamate: un lotto ne pesa al
#: più tanto, e il successivo parte dopo una pausa di ``_PAUSA_S``.
_CHIAMATE_PER_LOTTO = 500
_PAUSA_S = 60.0
#: Open-Meteo: una chiamata ogni due settimane di dati per località.
_GIORNI_PER_CHIAMATA = 14


def peso_per_nodo(window_days: int) -> float:
    """Chiamate che un nodo costa all'API pubblica per ``window_days`` di archivio."""
    return max(1.0, window_days / _GIORNI_PER_CHIAMATA)


def riferimento_del_punto(punto: dict[str, Any], *, percentile: float) -> tuple[bool, float | None]:
    """``(risposto, portata)``: ``risposto`` è falso per un punto di un lotto fallito."""
    if "daily" not in punto:
        return False, None
    valori = _floats((punto.get("daily") or {}).get("river_discharge"))
    if len(valori) < MIN_REFERENCE_DAYS:
        return True, None
    return True, percentile_of(valori, percentile)


async def riempi(
    *,
    chiamate: int,
    percentile: float = DEFAULT_REFERENCE_PERCENTILE,
    window_days: int = DEFAULT_REFERENCE_WINDOW_DAYS,
    client: OpenMeteoFloodClient | None = None,
    oggi: date | None = None,
    attendi: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, int]:
    """Calcola i riferimenti mancanti che ``chiamate`` può pagare e li salva. Rilanciabile."""
    peso = peso_per_nodo(window_days)
    limite = int(chiamate // peso)
    if limite == 0:
        return {"richiesti": 0, "salvati": 0, "con_fiume": 0}
    lotto_n = max(1, int(_CHIAMATE_PER_LOTTO // peso))
    nodi = await glofas_repo.da_calcolare(
        spacing=NODE_SPACING_DEG, percentile=percentile, window_days=window_days, limite=limite
    )
    client = client or OpenMeteoFloodClient()
    fine = (oggi or datetime.now(UTC).date()) - timedelta(days=1)
    salvati = con_fiume = 0
    for i in range(0, len(nodi), lotto_n):
        if i:
            await attendi(_PAUSA_S)
        if await _in_pausa():
            log.info("glofas.riferimenti.pausa", salvati=salvati, mancanti=len(nodi) - i)
            break
        lotto = nodi[i : i + lotto_n]
        punti = await client.fetch_grid(
            FLOOD_URL,
            lotto,
            {
                "daily": "river_discharge",
                "start_date": (fine - timedelta(days=window_days)).isoformat(),
                "end_date": fine.isoformat(),
                "timezone": "UTC",
            },
            "openmeteo.flood.discharge_reference",
        )
        righe: list[tuple[glofas_repo.Nodo, float | None]] = []
        for nodo, punto in zip(lotto, punti, strict=True):
            risposto, portata = riferimento_del_punto(punto, percentile=percentile)
            if risposto:
                righe.append((nodo, portata))
        salvati += await glofas_repo.salva(righe, percentile=percentile, window_days=window_days)
        con_fiume += sum(1 for _, p in righe if p is not None)
    log.info(
        "glofas.riferimenti.done",
        richiesti=len(nodi),
        salvati=salvati,
        con_fiume=con_fiume,
        percentile=percentile,
        window_days=window_days,
    )
    return {"richiesti": len(nodi), "salvati": salvati, "con_fiume": con_fiume}
