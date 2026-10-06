"""Correttore multi-modello della pioggia a 72 ore (#155, punto 1).

Due comandi:

``limen rain-ensemble-fetch`` raccoglie, per un campione di nodi sparsi
sull'Italia, la pioggia giornaliera prevista da cinque modelli con il suo
anticipo (API pubblica «previous runs») e quella caduta (ERA5 dall'istanza
propria). È fatto per girare a più riprese: ogni corsa prende al massimo
``LIMEN_RAIN_ENS_NODES_PER_RUN`` nodi nuovi, e un 429 la ferma senza perdere
quelli già scritti. Consuma il tetto pubblico, che è lo stesso di GloFAS.

``limen rain-ensemble-train`` addestra un LightGBM a quantili (10°, 50°, 90°)
sulla pioggia di 72 ore e lo confronta, con validazione su blocchi
geografici, con il modello singolo e con la media dei modelli. Non tocca il
punteggio: misura soltanto.

La previsione è quella emessa il giorno prima della finestra: i tre giorni
hanno anticipo 1, 2 e 3 (da 24 a 96 ore). È un po' più lontana delle 0-72 ore
operative, quindi il confronto è prudente, non indulgente.

Env: ``LIMEN_RAIN_ENS_NODES`` (campione, default 150),
``LIMEN_RAIN_ENS_NODES_PER_RUN`` (default 30), ``LIMEN_RAIN_ENS_START``
(default 2024-03-01), ``LIMEN_RAIN_ENS_END`` (default ieri meno 3 giorni).
"""

from __future__ import annotations

import math
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from limen.cli.fwi_backfill import _aoi_bbox, _int_env
from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.data.repos.fwi_state_repo import quantize
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.grid import build_snapped_nodes
from limen.integrations.openmeteo.previous_runs import (
    MODELLI,
    QuotaEsauritaError,
    previsioni_giornaliere,
)

log = get_logger(__name__)

#: Il passo del campione: lo stesso reticolo dell'FWI, che copre ogni AOI.
_PASSO = 0.25
#: Il seme del campione: fisso, perché le corse successive devono scegliere
#: gli stessi nodi.
_SEME = 155
#: La soglia del ramo pluviale dell'alluvione: è lì che l'errore conta.
SOGLIA_MM = 40.0
#: Il modello che fa le veci di quello operativo: l'istanza propria usa
#: `best_match`, che sull'Italia coincide con ICON (Trieste, 6 ottobre:
#: 107,8 contro 107,5 mm).
OPERATIVO = "icon_seamless"


def _date_env(nome: str, default: date) -> date:
    raw = os.getenv(nome)
    return date.fromisoformat(raw) if raw else default


async def _campione(n: int) -> list[tuple[float, float]]:
    nodi: set[tuple[float, float]] = set()
    for aoi_id in await list_aoi_ids():
        bbox = await _aoi_bbox(aoi_id)
        if bbox is not None:
            nodi.update(build_snapped_nodes(bbox, spacing=_PASSO))
    ordinati = sorted(nodi)
    return sorted(random.Random(_SEME).sample(ordinati, min(n, len(ordinati))))


async def _fatti() -> set[tuple[float, float]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT o.node_lon, o.node_lat FROM rain_ens_observed o "
            "JOIN rain_ens_forecast f USING (node_lon, node_lat)"
        )
    return {(float(r["node_lon"]), float(r["node_lat"])) for r in rows}


async def _scrivi(
    lon: float,
    lat: float,
    previste: dict[tuple[str, int], dict[date, float]],
    osservate: dict[date, float],
) -> None:
    kl, ka = quantize(lon, lat)
    async with acquire() as conn, conn.transaction():
        await conn.executemany(
            "INSERT INTO rain_ens_forecast (node_lon, node_lat, day, model, lead, mm) "
            "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING",
            [
                (kl, ka, g, modello, lead, mm)
                for (modello, lead), giorni in previste.items()
                for g, mm in giorni.items()
            ],
        )
        await conn.executemany(
            "INSERT INTO rain_ens_observed (node_lon, node_lat, day, mm) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
            [(kl, ka, g, mm) for g, mm in osservate.items()],
        )


async def _osservate(lon: float, lat: float, inizio: date, fine: date) -> dict[date, float]:
    serie = await OpenMeteoHttpClient().get_rainfall_grid(
        nodes=[(lon, lat)],
        window_start=datetime.combine(inizio, datetime.min.time(), UTC),
        window_end=datetime.combine(fine, datetime.max.time(), UTC),
        use_archive=True,
    )
    somme: dict[date, float] = defaultdict(float)
    ore: dict[date, int] = defaultdict(int)
    for s in serie[0] if serie else []:
        somme[s.timestamp.date()] += s.precipitation_mm
        ore[s.timestamp.date()] += 1
    return {g: max(v, 0.0) for g, v in somme.items() if ore[g] == 24}


async def run_fetch() -> int:
    n = max(_int_env("LIMEN_RAIN_ENS_NODES", 150), 1)
    per_corsa = max(_int_env("LIMEN_RAIN_ENS_NODES_PER_RUN", 30), 1)
    inizio = _date_env("LIMEN_RAIN_ENS_START", date(2024, 3, 1))
    # L'archivio ERA5 è indietro di qualche giorno sul tempo reale.
    fine = _date_env("LIMEN_RAIN_ENS_END", datetime.now(UTC).date() - timedelta(days=6))
    async with lifespan_pool():
        campione = await _campione(n)
        fatti = await _fatti()
        da_fare = [p for p in campione if (round(p[0], 4), round(p[1], 4)) not in fatti]
        log.info(
            "rain_ens.fetch.start", sample=len(campione), to_do=len(da_fare), per_run=per_corsa
        )
        scritti = 0
        for lon, lat in da_fare[:per_corsa]:
            try:
                previste = await previsioni_giornaliere(lon=lon, lat=lat, inizio=inizio, fine=fine)
            except QuotaEsauritaError:
                log.warning("rain_ens.fetch.quota", written=scritti)
                break
            osservate = await _osservate(lon, lat, inizio, fine)
            if not previste or not osservate:
                # Un nodo senza uno dei due lati non si scrive: resta da fare.
                log.warning("rain_ens.fetch.empty", lon=lon, lat=lat)
                continue
            await _scrivi(lon, lat, previste, osservate)
            scritti += 1
            log.info("rain_ens.fetch.node", lon=lon, lat=lat, done=scritti)
    await SharedHttpClient.aclose()
    log.info("rain_ens.fetch.done", written=scritti, remaining=max(len(da_fare) - scritti, 0))
    return 0


# --------------------------------------------------------------- addestramento


@dataclass(frozen=True, slots=True)
class Campione:
    lon: float
    lat: float
    giorno: date
    previsioni: dict[str, float]
    osservata: float


def campioni(
    previste: dict[tuple[float, float, str, int], dict[date, float]],
    osservate: dict[tuple[float, float], dict[date, float]],
) -> list[Campione]:
    """Le finestre di 72 ore: per ogni nodo e giorno d, la pioggia dei giorni
    d, d+1, d+2 prevista il giorno d-1 (anticipi 1, 2, 3) e quella caduta.

    Un modello entra in una finestra solo se ha tutti e tre i giorni; una
    finestra entra solo se ha almeno tre modelli e la pioggia osservata
    completa.
    """
    out: list[Campione] = []
    for (lon, lat), oss in osservate.items():
        for d in sorted(oss):
            giorni = [d + timedelta(days=i) for i in range(3)]
            if any(g not in oss for g in giorni):
                continue
            prev: dict[str, float] = {}
            for modello in MODELLI:
                parti = [
                    previste.get((lon, lat, modello, i + 1), {}).get(g)
                    for i, g in enumerate(giorni)
                ]
                if all(p is not None for p in parti):
                    prev[modello] = float(sum(p for p in parti if p is not None))
            if len(prev) >= 3:
                out.append(Campione(lon, lat, d, prev, sum(oss[g] for g in giorni)))
    return out


def blocco(lon: float, lat: float) -> tuple[int, int]:
    """Il blocco geografico di 2° di un nodo: la validazione non mescola
    nodi vicini fra addestramento e prova (nessuna fuga spaziale)."""
    return (math.floor(lon / 2.0), math.floor(lat / 2.0))


def caratteristiche(c: Campione) -> list[float]:
    valori = [c.previsioni.get(m, math.nan) for m in MODELLI]
    presenti = [v for v in valori if not math.isnan(v)]
    media = sum(presenti) / len(presenti)
    var = sum((v - media) ** 2 for v in presenti) / len(presenti)
    mese = c.giorno.month
    return [
        *valori,
        media,
        math.sqrt(var),
        max(presenti),
        min(presenti),
        math.sin(2 * math.pi * mese / 12),
        math.cos(2 * math.pi * mese / 12),
        c.lat,
        c.lon,
    ]


def punteggi(previste: list[float], osservate: list[float]) -> dict[str, float]:
    """Errore medio, errore e scarto sulle piogge forti, e la capacità di
    dire «sopra soglia» — con il tasso di base accanto, perché un modello che
    dice sempre «sopra» ha un tasso di successo perfetto e non serve."""
    n = len(osservate)
    forti = [(p, o) for p, o in zip(previste, osservate, strict=True) if o >= SOGLIA_MM]
    sopra_p = [p >= SOGLIA_MM for p in previste]
    sopra_o = [o >= SOGLIA_MM for o in osservate]
    colpiti = sum(a and b for a, b in zip(sopra_p, sopra_o, strict=True))
    allarmi = sum(sopra_p)
    eventi = sum(sopra_o)
    return {
        "mae": sum(abs(p - o) for p, o in zip(previste, osservate, strict=True)) / n,
        "mae_forti": sum(abs(p - o) for p, o in forti) / len(forti) if forti else math.nan,
        "bias_forti": sum(p - o for p, o in forti) / len(forti) if forti else math.nan,
        "colpiti": colpiti / eventi if eventi else math.nan,
        "falsi_allarmi": (allarmi - colpiti) / allarmi if allarmi else math.nan,
        "tasso_base": eventi / n,
        "allarmi_su_giorni": allarmi / n,
    }


async def _carica() -> tuple[
    dict[tuple[float, float, str, int], dict[date, float]],
    dict[tuple[float, float], dict[date, float]],
]:
    previste: dict[tuple[float, float, str, int], dict[date, float]] = defaultdict(dict)
    osservate: dict[tuple[float, float], dict[date, float]] = defaultdict(dict)
    async with acquire() as conn:
        for r in await conn.fetch(
            "SELECT node_lon, node_lat, day, model, lead, mm "
            "FROM rain_ens_forecast WHERE lead BETWEEN 1 AND 3"
        ):
            previste[(float(r["node_lon"]), float(r["node_lat"]), r["model"], int(r["lead"]))][
                r["day"]
            ] = float(r["mm"])
        for r in await conn.fetch("SELECT node_lon, node_lat, day, mm FROM rain_ens_observed"):
            osservate[(float(r["node_lon"]), float(r["node_lat"]))][r["day"]] = float(r["mm"])
    return previste, osservate


async def run_train() -> int:
    import lightgbm as lgb
    import numpy as np

    async with lifespan_pool():
        previste, osservate = await _carica()
    dati = campioni(previste, osservate)
    if len(dati) < 1000:
        log.warning("rain_ens.train.too_few", samples=len(dati))
        return 1
    x = np.array([caratteristiche(c) for c in dati])
    y = np.array([c.osservata for c in dati])
    blocchi = sorted({blocco(c.lon, c.lat) for c in dati})
    # Round-robin dei blocchi su cinque pieghe, come la validazione del ML
    # delle frane: mai una divisione casuale.
    piega_di = {b: i % 5 for i, b in enumerate(blocchi)}
    pieghe = np.array([piega_di[blocco(c.lon, c.lat)] for c in dati])

    q: dict[float, Any] = {a: np.zeros(len(y)) for a in (0.1, 0.5, 0.9)}
    for k in range(5):
        prova = pieghe == k
        for alfa in q:
            modello = lgb.LGBMRegressor(
                objective="quantile",
                alpha=alfa,
                n_estimators=300,
                learning_rate=0.05,
                num_leaves=31,
                min_child_samples=40,
                verbose=-1,
                n_jobs=8,
            )
            modello.fit(x[~prova], y[~prova])
            q[alfa][prova] = np.clip(modello.predict(x[prova]), 0.0, None)

    osservata = y.tolist()
    operativo = [c.previsioni.get(OPERATIVO, math.nan) for c in dati]
    con_operativo = [i for i, v in enumerate(operativo) if not math.isnan(v)]
    media = [sum(c.previsioni.values()) / len(c.previsioni) for c in dati]
    risultati = {
        "operativo_icon": punteggi(
            [operativo[i] for i in con_operativo], [osservata[i] for i in con_operativo]
        ),
        "media_modelli": punteggi(media, osservata),
        "correttore_mediana": punteggi(q[0.5].tolist(), osservata),
    }
    copertura = float(np.mean((y >= q[0.1]) & (y <= q[0.9])))
    log.info(
        "rain_ens.train.done",
        samples=len(dati),
        nodes=len(osservate),
        blocks=len(blocchi),
        interval_10_90_coverage=round(copertura, 3),
        **{f"{nome}.{k}": round(v, 3) for nome, r in risultati.items() for k, v in r.items()},
    )
    return 0


__all__ = [
    "Campione",
    "blocco",
    "campioni",
    "caratteristiche",
    "punteggi",
    "run_fetch",
    "run_train",
]
