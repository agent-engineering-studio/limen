"""Ricostruzione offline delle feature meteo dell'incendio (#68).

Ogni campione è una coppia (cella, istante) e al modello serve il **FWI di
quel giorno in quella cella**. Non si legge da una tabella: la catena di Van
Wagner è ricorsiva, quindi l'unico modo di avere l'indice del 12 agosto 2024 è
camminarci dentro dal seme, esattamente come fa il passo operativo.

Struttura opposta a quella dell'enricher pioggia, e per una ragione. Là si
raggruppa **per giorno** perché ogni campione vuole la sua finestra di trenta
giorni indietro; qui si raggruppa **per nodo** e si cammina l'intero intervallo,
perché la catena va percorsa comunque tutta e chiedere lo stesso nodo una volta
per giorno pagherebbe N volte lo stesso dato. L'intervallo si chiede però a
blocchi di un anno, portando lo stato della catena da un blocco al successivo:
i campioni coprono ogni giorno dal 2000, e ventiquattro anni orari per venticinque
nodi in una richiesta (~190 MB) superavano il timeout di lettura — ogni nodo
degradava e l'addestramento arricchiva zero campioni (#327).

Il seme, non `fwi_state`: rigiocare l'estate scorsa partendo dal codice di
siccità di oggi darebbe a agosto 2024 la memoria del 2026. Lo stesso motivo
per cui il backtest incendio non legge lo stato operativo.

**Le feature mancanti non diventano 0.** Il resto della pipeline degrada un
blocco assente a zero, ed è giusto per la pioggia — zero millimetri è una
lettura possibile. Per il FWI no: zero significa "nessun pericolo", quindi un
positivo non arricchito insegnerebbe al modello che quella cella ha bruciato
in un giorno senza pericolo. I campioni senza blocco `fire` completo restano
fuori dall'addestramento (vedi `fetch_enriched_samples`).

Idempotente: si arricchiscono solo i campioni il cui blocco `fire` non ha
ancora la parte meteo, quindi una ripresa riparte da dove si era fermata.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from limen.cli.fwi_backfill import params_from
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.core.scoring.wildfire.fwi import FwiState, advance
from limen.data.db import acquire
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import MeteoSnapshot
from limen.integrations.openmeteo.grid import build_snapped_nodes

log = get_logger(__name__)

#: Reticolo nazionale, così l'identità di un nodo non dipende dall'AOI —
#: la stessa promessa che `fwi_state` fa allo stato operativo.
_ITALY_BBOX = (6.6, 35.4, 18.6, 47.2)

#: Nodi per richiesta. Le coordinate viaggiano nella query string, e 677 punti
#: in una volta tornarono come qualcosa che non era JSON.
_NODE_BATCH = 25

#: Giorni per richiesta. Un anno per 25 nodi è ~8 MB e ~6 s dall'istanza
#: locale (misurato): ben dentro il timeout di lettura del client condiviso.
_CHUNK_DAYS = 366

#: Chiavi che il blocco `fire` deve avere per essere considerato completo.
#: La parte statica la scrive già l'estrazione; questa è la parte meteo.
WEATHER_KEYS = ("fwi", "isi", "dc")

#: Giorni di pioggia antecedente accumulati. Coincide con la finestra che il
#: vettore delle frane usa, così la stessa grandezza si legge alla stessa
#: scala nei due pericoli — con il segno opposto.
_RAIN_WINDOW_DAYS = 30


async def _pending(conn: Any, *, spacing: float) -> list[dict[str, Any]]:
    """Campioni incendio senza la parte meteo del blocco `fire`."""
    rows = await conn.fetch(
        """
        SELECT t.id, t.cell_id, t.valuation_time,
               ST_X(ST_Centroid(g.geom)) AS lon, ST_Y(ST_Centroid(g.geom)) AS lat
        FROM training_samples t
        JOIN grid_cells g ON g.id = t.cell_id
        WHERE t.hazard_type = 'wildfire'
          AND NOT (t.features -> 'fire' ? 'fwi')
        ORDER BY t.valuation_time
        """
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        item["node_key"] = _node_key(float(r["lon"]), float(r["lat"]), spacing=spacing)
        out.append(item)
    return out


def _node_key(lon: float, lat: float, *, spacing: float) -> tuple[int, int]:
    """Indice del punto di reticolo globale più vicino."""
    return (round(lon / spacing), round(lat / spacing))


class NodeChain:
    """La catena di un nodo, che si può camminare a pezzi.

    Lo stato (i tre codici, i giorni di catena e la pioggia recente) resta fra
    una chiamata e l'altra: percorrere un anno e poi il successivo dà gli
    stessi numeri che percorrerli insieme, ed è quello che permette di
    chiedere il meteo un anno alla volta. Ripete la logica di
    ``backtest_wildfire.replay_chain`` con un ritorno diverso — un dizionario
    di numeri invece di `FireWeatherState` — e non la riusa per non far
    dipendere il feature store da un modulo CLI. La ricorsione vera sta in
    `wildfire/fwi.advance`, che è una sola.
    """

    def __init__(self, thresholds: WildfireThresholds) -> None:
        self._thresholds = thresholds
        self._params = params_from(thresholds)
        self._state = FwiState(
            ffmc=self._params.ffmc_start, dmc=self._params.dmc_start, dc=self._params.dc_start
        )
        self._chain_days = 0
        # La pioggia dei trenta giorni precedenti viene dalla **stessa** fetch
        # che guida la catena: la precipitazione è già uno dei quattro ingressi
        # del FWI, quindi accumularla non costa una richiesta in più.
        # L'enricher pioggia non poteva darla — è legato a CERRA, che finisce
        # nel 2021 — e la feature sarebbe rimasta costante a zero, cioè una
        # colonna morta che nasconde le altre nello SHAP.
        self._rain_by_day: dict[date, float] = {}

    def walk(self, *, snapshot: MeteoSnapshot, days: list[date]) -> dict[date, dict[str, float]]:
        out: dict[date, dict[str, float]] = {}
        for day in days:
            obs = snapshot.noon_observation(
                day, noon_hour=self._thresholds.fwi.ora_osservazione_utc
            )
            if obs is None:
                continue
            self._rain_by_day[day] = obs.rain_24h_mm
            step = advance(
                self._state,
                month=day.month,
                temperature_c=obs.temperature_c,
                relative_humidity_pct=obs.relative_humidity_pct,
                wind_speed_kmh=obs.wind_speed_kmh,
                rain_24h_mm=obs.rain_24h_mm,
                params=self._params,
            )
            self._chain_days += 1
            window = [
                self._rain_by_day.get(day - timedelta(days=k), 0.0)
                for k in range(_RAIN_WINDOW_DAYS)
            ]
            out[day] = {
                "fwi": round(step.fwi, 3),
                "isi": round(step.isi, 3),
                "dc": round(step.state.dc, 3),
                "chain_days": float(self._chain_days),
                "rain_30d_mm": round(sum(window), 2),
            }
            self._state = step.state
        # Ventiquattro anni di giorni per venticinque nodi restano in memoria
        # per niente: alla finestra servono solo gli ultimi trenta.
        horizon = days[-1] - timedelta(days=_RAIN_WINDOW_DAYS) if days else None
        if horizon is not None:
            self._rain_by_day = {d: v for d, v in self._rain_by_day.items() if d > horizon}
        return out


def chain_for_days(
    *,
    snapshot: MeteoSnapshot,
    days: list[date],
    thresholds: WildfireThresholds,
) -> dict[date, dict[str, float]]:
    """Percorre la catena di un nodo dal seme e restituisce gli indici per giorno."""
    return NodeChain(thresholds).walk(snapshot=snapshot, days=days)


async def enrich_fire_features(*, batch_pause_s: float = 0.3) -> int:
    """Riempie la parte meteo di ``features.fire``. Ritorna i campioni scritti."""
    thresholds = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(thresholds, WildfireThresholds)
    spacing = thresholds.fwi.node_spacing_deg

    async with acquire() as conn:
        pending = await _pending(conn, spacing=spacing)
    if not pending:
        log.info("fire_enrich.nothing_to_do")
        return 0

    lattice = {
        _node_key(lon, lat, spacing=spacing): (lon, lat)
        for lon, lat in build_snapped_nodes(_ITALY_BBOX, spacing=spacing)
    }
    by_node: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for item in pending:
        by_node[item["node_key"]].append(item)

    spinup = timedelta(days=thresholds.fwi.spinup_days)
    client = OpenMeteoHttpClient()
    node_keys = sorted(by_node)
    log.info(
        "fire_enrich.start",
        pending=len(pending),
        nodes=len(node_keys),
        spacing=spacing,
        spinup_days=thresholds.fwi.spinup_days,
    )

    done = 0
    degraded_nodes = 0
    for offset in range(0, len(node_keys), _NODE_BATCH):
        batch = node_keys[offset : offset + _NODE_BATCH]
        # Un solo intervallo per lotto: la catena va percorsa comunque tutta,
        # quindi la finestra è quella che copre ogni campione del lotto.
        first = min(s["valuation_time"] for key in batch for s in by_node[key]).date()
        last = max(s["valuation_time"] for key in batch for s in by_node[key]).date()
        days = [
            (first - spinup) + timedelta(days=i)
            for i in range(((last - (first - spinup)).days) + 1)
        ]
        coords = {key: lattice.get(key, (key[0] * spacing, key[1] * spacing)) for key in batch}
        chains = {key: NodeChain(thresholds) for key in batch}
        by_day = {key: _group_by_day(by_node[key]) for key in batch}
        alive = list(batch)
        for start in range(0, len(days), _CHUNK_DAYS):
            chunk = days[start : start + _CHUNK_DAYS]
            if not alive:
                break
            series = await client.get_fire_weather_grid(
                nodes=[coords[key] for key in alive],
                window_start=datetime.combine(chunk[0] - timedelta(days=1), time.min, UTC),
                window_end=datetime.combine(chunk[-1], time.max, UTC),
                use_archive=True,
                batch_size=_NODE_BATCH,
            )
            writes: list[tuple[int, str, str]] = []
            still_alive: list[tuple[int, int]] = []
            for key, samples in zip(alive, series, strict=True):
                if not samples:
                    # Una catena interrotta non riparte: dal seme sarebbe
                    # un'altra catena. I blocchi già scritti restano buoni.
                    degraded_nodes += 1
                    continue
                still_alive.append(key)
                lon, lat = coords[key]
                chain = chains[key].walk(
                    snapshot=MeteoSnapshot(
                        centroid_lon=lon,
                        centroid_lat=lat,
                        window_start=datetime.combine(chunk[0], time.min, UTC),
                        window_end=datetime.combine(chunk[-1], time.max, UTC),
                        samples=samples,
                    ),
                    days=chunk,
                )
                for day in chunk:
                    items = by_day[key].get(day)
                    if not items:
                        continue
                    indices = chain.get(day)
                    if indices is None:
                        # Giorno senza osservazione: nessuna scrittura, così il
                        # campione resta "in attesa" invece di entrare
                        # nell'addestramento con un FWI inventato.
                        continue
                    fire_part = {k: v for k, v in indices.items() if k != "rain_30d_mm"}
                    rain_part = {"rain_30d_mm": indices["rain_30d_mm"]}
                    for item in items:
                        writes.append(
                            (int(item["id"]), json.dumps(fire_part), json.dumps(rain_part))
                        )
            alive = still_alive
            done += await _write(writes)
            await asyncio.sleep(batch_pause_s)
        log.info(
            "fire_enrich.progress",
            nodes_done=min(offset + _NODE_BATCH, len(node_keys)),
            nodes_total=len(node_keys),
            samples_done=done,
        )

    log.info("fire_enrich.done", enriched=done, degraded_nodes=degraded_nodes)
    return done


def _group_by_day(items: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    out: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        out[item["valuation_time"].date()].append(item)
    return out


async def _write(writes: list[tuple[int, str, str]]) -> int:
    if not writes:
        return 0
    async with acquire() as conn, conn.transaction():
        for sample_id, fire_payload, rain_payload in writes:
            await conn.execute(
                """
                UPDATE training_samples
                SET features = jsonb_set(
                        jsonb_set(
                            features,
                            '{fire}',
                            COALESCE(features -> 'fire', '{}'::jsonb) || $2::jsonb,
                            true
                        ),
                        '{rain}',
                        COALESCE(features -> 'rain', '{}'::jsonb) || $3::jsonb,
                        true
                    )
                WHERE id = $1
                """,
                sample_id,
                fire_payload,
                rain_payload,
            )
    return len(writes)


__all__ = ["WEATHER_KEYS", "NodeChain", "chain_for_days", "enrich_fire_features"]
