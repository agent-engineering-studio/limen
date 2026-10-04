"""``limen fwi-climatology`` — com'è di solito l'FWI, per nodo e per mese.

Cammina l'archivio ERA5 per più anni con la stessa catena e la stessa
lettura di mezzogiorno di `fwi-backfill`, e per ogni nodo del reticolo FWI
riassume i valori di ogni mese in 21 quantili (migrazione 061). Non tocca
`fwi_state`: la catena di qui è un calcolo a parte, che parte dal seme e
scarta i primi giorni di avviamento.

Lento per natura e fatto per girare una volta: misurato sull'istanza
propria, 100 nodi per un anno sono ~80 s, quindi l'Italia intera su dieci
anni sono alcune ore. Si riprende da dove si era fermato: i nodi che hanno
già i dodici mesi per lo stesso intervallo di anni si saltano.

* ``LIMEN_FWI_CLIM_YEARS`` — anni di archivio (default 10), fino all'ultimo
  anno intero.
* ``LIMEN_FWI_CLIM_AOI``   — una sola AOI; assente ⇒ tutte.
* ``LIMEN_FWI_CLIM_FORCE`` — ``1`` per ricalcolare anche i nodi già fatti.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from limen.cli.fwi_backfill import _aoi_bbox, _int_env, _observations, params_from
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds
from limen.core.scoring.wildfire.climatology import quantili
from limen.core.scoring.wildfire.fwi import FwiParams, FwiState, advance
from limen.data.db import lifespan_pool
from limen.data.repos import fwi_climatology_repo
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.data.repos.fwi_climatology_repo import NodoMese
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import FireWeatherObservation, MeteoSnapshot
from limen.integrations.openmeteo.grid import build_snapped_nodes

log = get_logger(__name__)

_LOTTO = 100
#: Giorni scartati all'inizio: la catena parte dal seme primaverile e il DC
#: ha una memoria di ~52 giorni.
_AVVIAMENTO = 60


def accumula(
    osservazioni: dict[date, FireWeatherObservation],
    giorni: list[date],
    params: FwiParams,
    stato: FwiState,
    avviati: int,
    per_mese: dict[int, list[float]],
) -> tuple[FwiState, int]:
    """Fa avanzare la catena su ``giorni`` e mette l'FWI di ogni giorno nel suo mese.

    Un giorno senza osservazione si salta, non si azzera: inventare una
    lettura inietterebbe un giorno di essiccazione finto che la ricorsione si
    porterebbe dietro per settimane. I primi ``_AVVIAMENTO`` giorni contano per
    la catena ma non per la distribuzione.
    """
    for giorno in giorni:
        obs = osservazioni.get(giorno)
        if obs is None:
            continue
        uscita = advance(
            stato,
            month=giorno.month,
            temperature_c=obs.temperature_c,
            relative_humidity_pct=obs.relative_humidity_pct,
            wind_speed_kmh=obs.wind_speed_kmh,
            rain_24h_mm=obs.rain_24h_mm,
            params=params,
        )
        stato = uscita.state
        avviati += 1
        if avviati > _AVVIAMENTO:
            per_mese[giorno.month].append(uscita.fwi)
    return stato, avviati


async def _lotto(
    nodi: list[tuple[float, float]],
    anni: range,
    params: FwiParams,
    client: OpenMeteoHttpClient,
) -> list[NodoMese]:
    stati: dict[tuple[float, float], FwiState] = dict.fromkeys(nodi, params.initial_state)
    avviati: dict[tuple[float, float], int] = dict.fromkeys(nodi, 0)
    mesi: dict[tuple[float, float], dict[int, list[float]]] = {n: defaultdict(list) for n in nodi}
    for anno in anni:
        primo, ultimo = date(anno, 1, 1), date(anno, 12, 31)
        giorni = [primo + timedelta(days=i) for i in range((ultimo - primo).days + 1)]
        serie = await client.get_fire_weather_grid(
            nodes=nodi,
            # Un giorno prima: la pioggia delle 24 ore del primo mezzogiorno
            # cade nelle ore del giorno precedente.
            window_start=datetime.combine(primo - timedelta(days=1), datetime.min.time(), UTC),
            window_end=datetime.combine(ultimo, datetime.max.time(), UTC),
            use_archive=True,
        )
        for nodo, campioni in zip(nodi, serie, strict=True):
            osservazioni = _observations(
                MeteoSnapshot(
                    centroid_lon=nodo[0],
                    centroid_lat=nodo[1],
                    window_start=datetime.combine(primo, datetime.min.time(), UTC),
                    window_end=datetime.combine(ultimo, datetime.max.time(), UTC),
                    samples=campioni,
                ),
                giorni,
            )
            stati[nodo], avviati[nodo] = accumula(
                osservazioni, giorni, params, stati[nodo], avviati[nodo], mesi[nodo]
            )
        log.info("fwi.climatology.year", year=anno, nodes=len(nodi))
    return [
        NodoMese(
            lon=nodo[0],
            lat=nodo[1],
            month=mese,
            days=len(valori),
            quantiles=quantili(valori),
            year_from=anni.start,
            year_to=anni.stop - 1,
        )
        for nodo, per_mese in mesi.items()
        for mese, valori in sorted(per_mese.items())
        if valori
    ]


async def run() -> int:
    loaded = load_hazard_thresholds(HazardType.WILDFIRE)
    if not isinstance(loaded, WildfireThresholds):
        log.error("fwi.climatology.bad_config", got=type(loaded).__name__)
        return 1
    thresholds: WildfireThresholds = loaded
    quanti = max(_int_env("LIMEN_FWI_CLIM_YEARS", 10), 1)
    ultimo_anno = datetime.now(UTC).year - 1
    anni = range(ultimo_anno - quanti + 1, ultimo_anno + 1)
    params = params_from(thresholds)
    client = OpenMeteoHttpClient()

    async with lifespan_pool():
        una = os.getenv("LIMEN_FWI_CLIM_AOI")
        aoi_ids = [una] if una else await list_aoi_ids()
        nodi_set: set[tuple[float, float]] = set()
        for aoi_id in aoi_ids:
            bbox = await _aoi_bbox(aoi_id)
            if bbox is not None:
                nodi_set.update(build_snapped_nodes(bbox, spacing=thresholds.fwi.node_spacing_deg))
        fatti = (
            set()
            if os.getenv("LIMEN_FWI_CLIM_FORCE") == "1"
            else await fwi_climatology_repo.nodi_fatti(anni.start, anni.stop - 1)
        )
        da_fare = sorted(n for n in nodi_set if (round(n[0], 4), round(n[1], 4)) not in fatti)
        log.info(
            "fwi.climatology.start",
            nodes=len(nodi_set),
            to_do=len(da_fare),
            years=f"{anni.start}-{anni.stop - 1}",
        )
        scritti = 0
        for i in range(0, len(da_fare), _LOTTO):
            righe = await _lotto(da_fare[i : i + _LOTTO], anni, params, client)
            scritti += await fwi_climatology_repo.upsert_many(righe)
            log.info(
                "fwi.climatology.batch",
                done=min(i + _LOTTO, len(da_fare)),
                of=len(da_fare),
                rows=scritti,
            )
    await SharedHttpClient.aclose()
    log.info("fwi.climatology.done", rows=scritti)
    return 0


__all__ = ["accumula", "run"]
