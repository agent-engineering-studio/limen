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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from limen.core.logging import get_logger
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


async def clima_aoi(
    *,
    aoi_id: str,
    bbox: tuple[float, float, float, float],
    anni: range,
    ore: int,
    quantile: float,
    client: OpenMeteoHttpClient,
) -> list[tuple[float, float, float | None]] | None:
    """I riferimenti dei nodi, o ``None`` se l'archivio non ha dato ogni anno.

    Una serie vuota è una richiesta fallita (l'archivio ERA5 copre anche il
    mare): accettarla calcolerebbe il quantile su meno anni, e l'AOI salvata
    come fatta non verrebbe più riscaricata.
    """
    nodes = build_rain_nodes(bbox, spacing=_PASSO_NODI)
    out: list[tuple[float, float, float | None]] = []
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
        log.info("clima_pioggia.gruppo", aoi_id=aoi_id, fatti=len(out), nodi=len(nodes))
    return out


async def run() -> int:
    path = Path(os.getenv(CLIMA_ENV, CLIMA_DEFAULT))
    da = int(os.getenv("LIMEN_CLIMA_DA", "1995"))
    a = int(os.getenv("LIMEN_CLIMA_A", "2007"))
    anni = range(da, a + 1)
    ore = int(os.getenv("LIMEN_CLIMA_ORE", "24"))
    quantile = float(os.getenv("LIMEN_CLIMA_QUANTILE", "0.999"))
    parametri = {"ore": ore, "quantile": quantile, "anni": [anni.start, anni.stop - 1]}

    clima = leggi(path)
    if {k: clima.get(k) for k in parametri} != parametri:
        # Parametri diversi: i riferimenti vecchi non si mescolano ai nuovi.
        clima = {**parametri, "aoi": {}}

    client = OpenMeteoHttpClient()
    esito = 0
    async with lifespan_pool():
        one = os.getenv("LIMEN_CLIMA_AOI")
        aoi_ids = [one] if one else await list_aoi_ids()
        for aoi_id in aoi_ids:
            if aoi_id in clima["aoi"]:
                log.info("clima_pioggia.skip", aoi_id=aoi_id)
                continue
            aoi = await get_aoi(aoi_id)
            if aoi is None:
                log.warning("clima_pioggia.aoi_missing", aoi_id=aoi_id)
                continue
            minx, miny, maxx, maxy = aoi.bbox.bounds
            nodi = await clima_aoi(
                aoi_id=aoi_id,
                bbox=(minx, miny, maxx, maxy),
                anni=anni,
                ore=ore,
                quantile=quantile,
                client=client,
            )
            if nodi is None:
                esito = 1
                continue
            clima["aoi"][aoi_id] = [[lon, lat, mm] for lon, lat, mm in nodi]
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


__all__ = ["CLIMA_DEFAULT", "CLIMA_ENV", "quantile_cumulata", "riferimenti_aoi", "run"]
