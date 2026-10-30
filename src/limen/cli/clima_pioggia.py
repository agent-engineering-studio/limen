"""``limen clima-pioggia`` — la climatologia della cumulata di pioggia per nodo (#243).

Il metro dell'innesco ``cumulata`` di ``landslide.yaml``: per ogni nodo di
pioggia di un'AOI, il quantile della cumulata su ``ore`` ore, campionata ogni
6 ore sugli anni dell'archivio. Una soglia in millimetri non vale in tutte le
regioni — il 99° percentile delle 24 ore va da 19 mm in Sardegna a 38 in
Liguria — e divisa per il riferimento del suo nodo sì: sulle dodici finestre
della #122, la soglia nazionale scelta sulle regioni di taratura coglie in
verifica il 62-65 % delle frane invece del 15 %.

I nodi sono quelli di ``limen backtest`` (``build_rain_nodes`` sul bbox
dell'AOI, stesso passo), così ogni cella trova il suo riferimento senza
interpolare. Gli anni di default finiscono prima della prima finestra di
backtest (2008): un riferimento che contiene le frane da verificare le
renderebbe ordinarie.

Dallo stesso download esce il riferimento della pioggia antecedente (#357):
per nodo e per mese, media e deviazione standard della somma a ``api.horizon_days`` giorni
(la stessa che lo sweep passa al motore come ``api_30_mm``). Lo stesso mese
di pioggia è normale in Liguria ed eccezionale in Puglia, e il motore lo
leggeva contro un riferimento nazionale fisso.

Non è ``limen rain-climatology``: quella scrive ``pioggia_climatologia``
(migrazione 065), che l'alluvione legge in produzione, con gli ultimi dieci
anni interi — dentro cui cadono le finestre da verificare — e una riga sola
per nodo. Il risultato qui è un file JSON (``LIMEN_CLIMA_PIOGGIA``), perché
per ora lo legge solo il backtest. Rieseguire salta le AOI già calcolate con
gli stessi parametri.

Env knobs:

* ``LIMEN_CLIMA_AOI``      — una AOI; assente ⇒ tutte quelle del seed.
* ``LIMEN_CLIMA_PIOGGIA``  — il file (default ``data/clima_pioggia.json``).
* ``LIMEN_CLIMA_DA`` / ``_A`` — primo e ultimo anno (default 1995-2007).
* ``LIMEN_CLIMA_ORE``      — la finestra della cumulata (default 24).
* ``LIMEN_CLIMA_QUANTILE`` — il quantile (default 0,999).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from limen.core.logging import get_logger
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import lifespan_pool
from limen.data.repos.aoi_repo import get_aoi, list_aoi_ids
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.grid import build_rain_nodes

log = get_logger(__name__)

#: Il passo del reticolo di pioggia di `limen backtest` (`_RAIN_NODE_DEG`).
_PASSO_NODI = 0.1
_CAMPIONE_ORE = 6
_NODI_PER_GRUPPO = 50

CLIMA_ENV = "LIMEN_CLIMA_PIOGGIA"
CLIMA_DEFAULT = "data/clima_pioggia.json"


def quantile_cumulata(orarie: list[np.ndarray], *, ore: int, quantile: float) -> float | None:
    """Il quantile della cumulata su ``ore`` ore, una serie oraria per anno.

    Ogni anno si cumula da solo: la finestra non scavalca il buco fra il 31
    dicembre di un anno e il 1° gennaio di uno non contiguo. ``None`` se non
    c'è un solo valore, o se il quantile è zero (un nodo in mare aperto, o un
    archivio che ha risposto con soli null).
    """
    valori = [
        np.convolve(h, np.ones(ore), "valid")[::_CAMPIONE_ORE] for h in orarie if h.size >= ore
    ]
    if not valori:
        return None
    q = float(np.quantile(np.concatenate(valori), quantile))
    return q if q > 0 else None


Mensile = tuple[tuple[float, float] | None, ...]


def clima_api(orarie: list[np.ndarray], *, primo_anno: int, giorni: int) -> Mensile:
    """Media e deviazione standard, per mese, della pioggia sui ``giorni`` giorni prima.

    ``orarie`` sono anni **contigui** a partire da ``primo_anno``, una serie
    oraria UTC per anno dal 1° gennaio: a differenza della cumulata, la somma
    scavalca il capodanno, perché i primi di gennaio hanno anche loro un
    dicembre alle spalle. Il valore di un giorno va al mese di quel giorno,
    come lo sweep lo legge il giorno della valutazione. ``None`` per un mese
    senza campioni.
    """
    giornaliere = [h[: h.size // 24 * 24].reshape(-1, 24).sum(axis=1) for h in orarie]
    serie = np.concatenate(giornaliere) if giornaliere else np.array([])
    if serie.size < giorni:
        return (None,) * 12
    somme = np.convolve(serie, np.ones(giorni), "valid")
    inizio = date(primo_anno, 1, 1)
    mesi = np.array([(inizio + timedelta(days=giorni - 1 + k)).month for k in range(somme.size)])
    out: list[tuple[float, float] | None] = []
    for m in range(1, 13):
        valori = somme[mesi == m]
        out.append((float(valori.mean()), float(valori.std())) if valori.size else None)
    return tuple(out)


def leggi(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def riferimenti_aoi(
    clima: dict[str, Any], aoi_id: str, *, ore: int
) -> list[tuple[float, float, float | None]] | None:
    """I riferimenti di un'AOI, se il file li ha calcolati per questa finestra."""
    if clima.get("ore") != ore or aoi_id not in clima.get("aoi", {}):
        return None
    return [(float(lon), float(lat), mm) for lon, lat, mm in clima["aoi"][aoi_id]]


def riferimenti_api(
    clima: dict[str, Any], aoi_id: str, *, giorni: int
) -> list[tuple[float, float, Mensile]] | None:
    """Media e deviazione mensili della pioggia antecedente per nodo, se calcolate."""
    if clima.get("api_giorni") != giorni or aoi_id not in clima.get("api", {}):
        return None
    return [
        (float(lon), float(lat), tuple((x[0], x[1]) if x is not None else None for x in mesi))
        for lon, lat, mesi in clima["api"][aoi_id]
    ]


async def clima_aoi(
    *,
    aoi_id: str,
    bbox: tuple[float, float, float, float],
    anni: range,
    ore: int,
    quantile: float,
    giorni_api: int,
    client: OpenMeteoHttpClient,
) -> tuple[list[tuple[float, float, float | None]], list[tuple[float, float, Mensile]]] | None:
    """I riferimenti dei nodi (cumulata e pioggia antecedente), o ``None`` se
    l'archivio non ha dato ogni anno.

    Una serie vuota è una richiesta fallita (l'archivio ERA5 copre anche il
    mare): accettarla calcolerebbe il quantile su meno anni, e l'AOI salvata
    come fatta non verrebbe più riscaricata.
    """
    nodes = build_rain_nodes(bbox, spacing=_PASSO_NODI)
    out: list[tuple[float, float, float | None]] = []
    api: list[tuple[float, float, Mensile]] = []
    # A gruppi di nodi, e i quantili di un gruppo prima del successivo: un
    # anno orario è ~9.000 campioni per nodo, e la Lombardia intera (800 nodi)
    # tenuta in memoria per un anno ha superato 6 GB ed è stata uccisa.
    for k in range(0, len(nodes), _NODI_PER_GRUPPO):
        gruppo = nodes[k : k + _NODI_PER_GRUPPO]
        orarie: list[list[np.ndarray]] = [[] for _ in gruppo]
        for anno in anni:
            grid = await client.get_rainfall_grid(
                nodes=gruppo,
                window_start=datetime(anno, 1, 1, tzinfo=UTC),
                window_end=datetime(anno, 12, 31, 23, tzinfo=UTC),
                # Un anno orario per nodo pesa ~9.000 valori: a 100 nodi per
                # richiesta la risposta supera le decine di MB.
                batch_size=25,
            )
            serie_anno = grid[: len(gruppo)]
            if len(serie_anno) < len(gruppo) or not all(serie_anno):
                log.warning("clima_pioggia.incompleto", aoi_id=aoi_id, anno=anno, da_nodo=k)
                return None
            for i, serie in enumerate(serie_anno):
                orarie[i].append(np.array([s.precipitation_mm for s in serie]))
        out.extend(
            (lon, lat, quantile_cumulata(o, ore=ore, quantile=quantile))
            for (lon, lat), o in zip(gruppo, orarie, strict=True)
        )
        api.extend(
            (lon, lat, clima_api(o, primo_anno=anni.start, giorni=giorni_api))
            for (lon, lat), o in zip(gruppo, orarie, strict=True)
        )
        log.info("clima_pioggia.gruppo", aoi_id=aoi_id, fatti=len(out), nodi=len(nodes))
    return out, api


async def run() -> int:
    path = Path(os.getenv(CLIMA_ENV, CLIMA_DEFAULT))
    da = int(os.getenv("LIMEN_CLIMA_DA", "1995"))
    a = int(os.getenv("LIMEN_CLIMA_A", "2007"))
    anni = range(da, a + 1)
    ore = int(os.getenv("LIMEN_CLIMA_ORE", "24"))
    quantile = float(os.getenv("LIMEN_CLIMA_QUANTILE", "0.999"))
    giorni_api = load_regional_thresholds().api.horizon_days
    parametri = {
        "ore": ore,
        "quantile": quantile,
        "anni": [anni.start, anni.stop - 1],
        "api_giorni": giorni_api,
    }

    clima = leggi(path)
    if {k: clima.get(k) for k in parametri} != parametri:
        # Parametri diversi: i riferimenti vecchi non si mescolano ai nuovi.
        clima = {**parametri, "aoi": {}, "api": {}}

    client = OpenMeteoHttpClient()
    esito = 0
    async with lifespan_pool():
        one = os.getenv("LIMEN_CLIMA_AOI")
        aoi_ids = [one] if one else await list_aoi_ids()
        for aoi_id in aoi_ids:
            if aoi_id in clima["aoi"] and aoi_id in clima["api"]:
                log.info("clima_pioggia.skip", aoi_id=aoi_id)
                continue
            aoi = await get_aoi(aoi_id)
            if aoi is None:
                log.warning("clima_pioggia.aoi_missing", aoi_id=aoi_id)
                continue
            minx, miny, maxx, maxy = aoi.bbox.bounds
            calcolati = await clima_aoi(
                aoi_id=aoi_id,
                bbox=(minx, miny, maxx, maxy),
                anni=anni,
                ore=ore,
                quantile=quantile,
                giorni_api=giorni_api,
                client=client,
            )
            if calcolati is None:
                esito = 1
                continue
            nodi, api = calcolati
            clima["aoi"][aoi_id] = [[lon, lat, mm] for lon, lat, mm in nodi]
            clima["api"][aoi_id] = [[lon, lat, list(mesi)] for lon, lat, mesi in api]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(clima), encoding="utf-8")
            noti = [mm for _, _, mm in nodi if mm is not None]
            log.info(
                "clima_pioggia.aoi.done",
                aoi_id=aoi_id,
                nodi=len(nodi),
                senza_riferimento=len(nodi) - len(noti),
                mediana_mm=round(float(np.median(noti)), 1) if noti else None,
                file=str(path),
            )
    await SharedHttpClient.aclose()
    return esito


__all__ = [
    "CLIMA_DEFAULT",
    "CLIMA_ENV",
    "clima_api",
    "quantile_cumulata",
    "riferimenti_aoi",
    "riferimenti_api",
    "run",
]
