"""Open-Meteo dedicated flood/marine signals (issue #8).

Three forward-looking signals for the dynamic flood factor, each degrading to
``None`` independently (neutral degradation — never raises on a read):

* **pluvial** — forecast 72 h cumulated rain (forecast API);
* **fluvial** — peak river discharge against a normal (Flood API, GloFAS).
  Two normals, deliberately: the AOI-level signal keeps the trailing-month
  mean it was calibrated with for the landslide H component, the per-node one
  divides by each node's own ordinary high flow, which is the only way the
  number means the same thing on the Po and on its tributaries (#108);
* **coastal** — normalised wave height (Marine API; ``None`` inland).

These are combined with the ISPRA static hydraulic hazard by the pure scoring
factor in :mod:`limen.core.scoring.flood_forecast`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

# Wave height (m) mapped to the maximal coastal signal (1.0).
_WAVE_REF_M = 4.0

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


class _Cache(Protocol):
    """La parte di ``DistributedCache`` che serve qui.

    Dichiarata invece che importata: il client è un modulo di integrazione e
    non deve tirarsi dietro il livello dati per una firma.
    """

    async def get_json(self, key: str) -> Any | None: ...

    async def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None: ...


@dataclass(frozen=True, slots=True)
class FloodSignals:
    rain_72h_mm: float | None = None
    river_discharge_ratio: float | None = None
    coastal_surge_norm: float | None = None
    #: Per-node signals, present only when ``per_node`` was requested. The
    #: AOI-level scalars above stay for the landslide H component, which has
    #: always used them; the flood hazard reads these, because a single number
    #: copied onto every cell of a region is exactly the failure this repo
    #: already documented for rainfall (13 mm at the Puglia centroid against
    #: 77 mm at the cells that actually failed).
    nodes: tuple[tuple[float, float], ...] = ()
    rain_by_node: tuple[float | None, ...] = ()
    #: Attenzione: questo rapporto **non** è lo stesso di
    #: ``river_discharge_ratio`` qui sopra. Quello, che alimenta il componente
    #: H delle frane, è il picco previsto sulla media dei 31 giorni
    #: precedenti; questo è il picco sulla piena ordinaria del nodo (#108). Il
    #: primo resta com'è perché cambiarlo sposterebbe il campione V1 senza un
    #: backtest; le soglie del secondo stanno in `flood.yaml` e sono tarate su
    #: questa definizione.
    river_ratio_by_node: tuple[float | None, ...] = ()


#: Passo del reticolo su cui i due segnali dell'alluvione sono campionati.
#: Misurato sulla Basilicata: a 0.25° (~25 km) solo 2 nodi su 35 cadono su un
#: corso d'acqua modellato da GloFAS, quindi quasi nessuna cella riceverebbe il
#: segnale fluviale; a 0.1° sono 20 su 176. Più fitto non regge una sola
#: richiesta — 0.05° fa 677 punti e l'API risponde con qualcosa che non è
#: JSON — ed è anche il motivo per cui le richieste vanno a lotti.
_NODE_SPACING_DEG = 0.1

#: Punti per richiesta. Lo stesso limite che usa la griglia di pioggia.
_GRID_BATCH = 100

#: Come la degradazione condivisa, più `ValueError`: una richiesta troppo
#: grande risponde con un corpo che non è JSON, e `resp.json()` alza di lì.
_GRID_DEGRADATION_EXC: tuple[type[BaseException], ...] = (*_DEGRADATION_EXC, ValueError)

#: Giorni minimi perché il percentile di riferimento di un nodo sia un numero
#: e non un artefatto della stagione in cui è stato calcolato.
MIN_REFERENCE_DAYS = 365

#: Come si misura la piena ordinaria di un nodo. I valori operativi stanno in
#: `config/hazards/flood.yaml` e il workflow li passa da lì; questi sono per i
#: chiamanti diretti del client e devono restare gli stessi numeri.
DEFAULT_REFERENCE_PERCENTILE = 0.90
DEFAULT_REFERENCE_WINDOW_DAYS = 730

#: Per quanto il riferimento resta valido in cache. La piena ordinaria di un
#: fiume è una proprietà del bacino, non del meteo di questa settimana: un
#: mese è già frequente, e ricalcolarlo a ogni sweep costerebbe due anni di
#: archivio per ogni nodo ogni ora.
_REFERENCE_TTL_SECONDS = 30 * 24 * 3600


def _centroid(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    return ((min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0)


def _floats(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []
    return [float(v) for v in values if v is not None]


def _reference_key(nodes: list[tuple[float, float]], *, percentile: float, window_days: int) -> str:
    fingerprint = ";".join(f"{lon:.4f},{lat:.4f}" for lon, lat in nodes)
    digest = sha256(f"{percentile}:{window_days}:{fingerprint}".encode()).hexdigest()[:32]
    return f"flood:discharge_reference:{digest}"


def percentile_of(values: list[float], p: float) -> float | None:
    """Percentile per interpolazione lineare. ``None`` su serie vuota."""
    if not values:
        return None
    ordered = sorted(values)
    pos = p * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


class OpenMeteoFloodClient:
    """Fetches the dedicated flood/marine signals. All methods degrade to None."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache: _Cache | None = None,
    ) -> None:
        self._http = http_client
        self._cache = cache

    async def _client(self) -> httpx.AsyncClient:
        return self._http if self._http is not None else await SharedHttpClient.get()

    async def _get(self, url: str, params: dict[str, Any], label: str) -> dict[str, Any] | None:
        try:
            resp = await fetch_with_retry("GET", url, client=await self._client(), params=params)
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded", label=label, error=str(exc), error_type=type(exc).__name__
            )
            return None
        payload = resp.json()
        return payload if isinstance(payload, dict) else None

    async def fetch_grid(
        self,
        url: str,
        nodes: list[tuple[float, float]],
        params: dict[str, Any],
        label: str,
    ) -> list[dict[str, Any]]:
        """A multi-coordinate request, in batches. Open-Meteo answers with an array.

        Separate from :meth:`_get`, which narrows to ``dict`` and would drop
        the whole response on the floor.

        Public because the flood backtest needs the same batching against the
        historical endpoints: duplicating it there would duplicate the 677-point
        lesson below, and one of the two copies would eventually lose it.

        Batched because the coordinates travel in the query string: 677 points
        came back as something that was not JSON at all. A failed batch
        contributes empty dicts rather than shortening the list, so the
        caller's positional mapping onto nodes stays aligned.
        """
        out: list[dict[str, Any]] = []
        for i in range(0, len(nodes), _GRID_BATCH):
            batch = nodes[i : i + _GRID_BATCH]
            batch_params = {
                **params,
                "latitude": ",".join(f"{lat:.4f}" for _, lat in batch),
                "longitude": ",".join(f"{lon:.4f}" for lon, _ in batch),
            }
            try:
                resp = await fetch_with_retry(
                    "GET", url, client=await self._client(), params=batch_params
                )
                payload = resp.json()
            except _GRID_DEGRADATION_EXC as exc:
                # ValueError copre un corpo che non è JSON: una richiesta
                # sovradimensionata risponde così, e uno sweep deve degradare.
                log.warning(
                    "integration.degraded",
                    label=label,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    batch_size=len(batch),
                )
                out.extend({} for _ in batch)
                continue
            if isinstance(payload, list):
                points: list[dict[str, Any]] = [p if isinstance(p, dict) else {} for p in payload]
            elif isinstance(payload, dict):
                points = [payload]
            else:
                points = []
            if len(points) != len(batch):
                log.warning(
                    "openmeteo.flood.batch_size_mismatch",
                    label=label,
                    expected=len(batch),
                    got=len(points),
                )
                out.extend({} for _ in batch)
                continue
            out.extend(points)
        return out

    async def fetch_signals(
        self,
        *,
        bbox: tuple[float, float, float, float],
        valuation_time: datetime,
        horizon_hours: int = 72,
        per_node: bool = False,
        reference_percentile: float = DEFAULT_REFERENCE_PERCENTILE,
        reference_window_days: int = DEFAULT_REFERENCE_WINDOW_DAYS,
    ) -> FloodSignals:
        """The three AOI-level signals, plus per-node ones when asked.

        ``per_node`` exists because both dynamic signals are useless as a
        single number per region once they *are* the engine. The centroid of
        an AOI almost never sits on a river GloFAS models (measured: 0.0 for
        Basilicata), and a centroid rain reading misses the convective cell
        that actually floods somewhere else.

        Off by default **on purpose**: the landslide champion has been scored
        with the centroid scalars, and changing them under the same names
        would move V1's numbers without a backtest.
        """
        lon, lat = _centroid(bbox)
        signals = FloodSignals(
            rain_72h_mm=await self._pluvial(lon, lat, valuation_time, horizon_hours),
            river_discharge_ratio=await self._fluvial(lon, lat),
            coastal_surge_norm=await self._coastal(lon, lat),
        )
        if not per_node:
            return signals

        from limen.integrations.openmeteo.grid import build_snapped_nodes

        nodes = build_snapped_nodes(bbox, spacing=_NODE_SPACING_DEG)
        rain = await self._pluvial_by_node(nodes, valuation_time, horizon_hours)
        reference = await self._cached_reference(
            nodes,
            percentile=reference_percentile,
            window_days=reference_window_days,
        )
        rivers = await self._fluvial_by_node(nodes, reference=reference)
        return replace(
            signals,
            nodes=tuple(nodes),
            rain_by_node=tuple(rain),
            river_ratio_by_node=tuple(rivers),
        )

    async def _pluvial(
        self, lon: float, lat: float, t0: datetime, horizon_hours: int
    ) -> float | None:
        end = (t0 + timedelta(hours=horizon_hours)).date()
        payload = await self._get(
            FORECAST_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": "precipitation",
                "start_date": t0.date().isoformat(),
                "end_date": end.isoformat(),
                "timezone": "UTC",
            },
            "openmeteo.flood.pluvial",
        )
        if payload is None:
            return None
        nums = _floats((payload.get("hourly") or {}).get("precipitation"))
        return sum(nums) if nums else None

    async def _fluvial(self, lon: float, lat: float) -> float | None:
        """GloFAS: peak forecast discharge (next 7 d) / recent normal (past ~30 d)."""
        payload = await self._get(
            FLOOD_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "daily": "river_discharge",
                "past_days": 31,
                "forecast_days": 7,
                "timezone": "UTC",
            },
            "openmeteo.flood.fluvial",
        )
        if payload is None:
            return None
        vals = _floats((payload.get("daily") or {}).get("river_discharge"))
        if len(vals) < 8:
            return None
        past, future = vals[:-7], vals[-7:]
        baseline = sum(past) / len(past) if past else 0.0
        if baseline <= 0.0 or not future:
            return None
        return max(future) / baseline

    async def _pluvial_by_node(
        self, nodes: list[tuple[float, float]], t0: datetime, horizon_hours: int
    ) -> list[float | None]:
        """Forecast rain over ``horizon_hours`` at each node, in one request.

        Hour-bounded, not day-bounded: summing whole calendar days from
        ``t0.date()`` would stretch a 72 h window to as much as 96 h, and the
        thresholds it feeds are stated per window.
        """
        end = t0 + timedelta(hours=horizon_hours)
        results = await self.fetch_grid(
            FORECAST_URL,
            nodes,
            {
                "hourly": "precipitation",
                "start_date": t0.date().isoformat(),
                "end_date": end.date().isoformat(),
                "timezone": "UTC",
            },
            "openmeteo.flood.pluvial_grid",
        )
        if len(results) != len(nodes):
            return [None] * len(nodes)
        out: list[float | None] = []
        for point in results:
            hourly = point.get("hourly") or {}
            stamps = hourly.get("time") if isinstance(hourly.get("time"), list) else []
            values = _floats(hourly.get("precipitation"))
            if not stamps or len(values) != len(stamps):
                out.append(sum(values) if values else None)
                continue
            total = 0.0
            seen = False
            for stamp, mm in zip(stamps, values, strict=False):
                when = datetime.fromisoformat(str(stamp))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                if t0 <= when <= end:
                    total += mm
                    seen = True
            out.append(total if seen else None)
        return out

    async def _cached_reference(
        self, nodes: list[tuple[float, float]], *, percentile: float, window_days: int
    ) -> list[float | None]:
        """Il riferimento per nodo, letto dalla cache o ricalcolato.

        Una chiave sola per reticolo e non una per nodo: i nodi si leggono
        tutti insieme a ogni sweep, e 675 SELECT per un dato che cambia una
        volta al mese sarebbero 675 andate e ritorni sprecati. Un reticolo
        diverso (altro AOI, altro passo) è un'altra chiave.

        Cache irraggiungibile ⇒ si ricalcola: più lento, mai sbagliato.
        """
        key = _reference_key(nodes, percentile=percentile, window_days=window_days)
        cache = self._cache
        if cache is None:
            from limen.data.caching.postgres_cache import PostgresCache

            cache = PostgresCache()
        try:
            cached = await cache.get_json(key)
        except Exception as exc:
            log.warning(
                "integration.degraded",
                label="openmeteo.flood.reference_cache",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            cached = None
        if isinstance(cached, list) and len(cached) == len(nodes):
            return [float(v) if v is not None else None for v in cached]

        reference = await self.discharge_reference(
            nodes, percentile=percentile, window_days=window_days
        )
        known = sum(1 for r in reference if r is not None)
        log.info(
            "openmeteo.flood.reference_computed",
            nodes=len(nodes),
            with_reference=known,
            percentile=percentile,
            window_days=window_days,
        )
        if known:
            try:
                await cache.set_json(key, reference, ttl_seconds=_REFERENCE_TTL_SECONDS)
            except Exception as exc:
                log.warning(
                    "integration.degraded",
                    label="openmeteo.flood.reference_cache",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
        return reference

    async def discharge_reference(
        self,
        nodes: list[tuple[float, float]],
        *,
        percentile: float,
        window_days: int,
        today: date | None = None,
    ) -> list[float | None]:
        """Each node's own ordinary high flow, in m³/s (``None`` if unknown).

        A percentile of the node's own multi-year daily discharge, from the
        GloFAS archive. It is what makes the ratio comparable between a
        tributary and the Po, and it is fetched rarely -- the caller caches
        it, because a river's ordinary high flow does not move week to week.
        """
        end = (today or datetime.now(UTC).date()) - timedelta(days=1)
        results = await self.fetch_grid(
            FLOOD_URL,
            nodes,
            {
                "daily": "river_discharge",
                "start_date": (end - timedelta(days=window_days)).isoformat(),
                "end_date": end.isoformat(),
                "timezone": "UTC",
            },
            "openmeteo.flood.discharge_reference",
        )
        if len(results) != len(nodes):
            return [None] * len(nodes)
        out: list[float | None] = []
        for point in results:
            vals = _floats((point.get("daily") or {}).get("river_discharge"))
            # Una serie corta non è un riferimento: meglio nessun segnale che
            # un percentile calcolato su due settimane di magra.
            out.append(percentile_of(vals, percentile) if len(vals) >= MIN_REFERENCE_DAYS else None)
        return out

    async def _fluvial_by_node(
        self,
        nodes: list[tuple[float, float]],
        *,
        reference: list[float | None],
    ) -> list[float | None]:
        """Forecast peak discharge over each node's own ordinary high flow.

        Il riferimento è **del nodo**, non dell'AOI, ed è questo che rende il
        numero confrontabile fra corsi d'acqua di taglia diversa. La versione
        precedente rapportava il picco alla media dei 31 giorni precedenti e
        scartava i rigagnoli con una soglia relativa al massimo dell'AOI:
        misurato in Emilia-Romagna, il 10 % del Po vale 186 m³/s e lasciava
        vivi 4 nodi su 105 — Lamone, Senio e Montone, cioè i fiumi esondati
        nel 2023 e nel 2024, classificati come fossi (#108).

        Il filtro non serve più perché la patologia non c'è più. Sui due anni
        2023-2024 la quota di giorni-nodo sopra la soglia di normalità era
        ~40 % in **ogni** classe di portata — fossi e fiumi allo stesso modo —
        col rapporto sulla media mensile; col percentile del nodo scende al
        10-13 % ed è omogenea (Po 2 %).

        ``None`` dove il riferimento manca: "non so quanto è grande questo
        corso d'acqua" non è "il fiume è in secca".
        """
        results = await self.fetch_grid(
            FLOOD_URL,
            nodes,
            {
                "daily": "river_discharge",
                "forecast_days": 7,
                "timezone": "UTC",
            },
            "openmeteo.flood.fluvial_grid",
        )
        if len(results) != len(nodes) or len(reference) != len(nodes):
            return [None] * len(nodes)
        out: list[float | None] = []
        for point, ref in zip(results, reference, strict=True):
            future = _floats((point.get("daily") or {}).get("river_discharge"))
            if ref is None or ref <= 0.0 or not future:
                out.append(None)
                continue
            out.append(max(future) / ref)
        return out

    async def _coastal(self, lon: float, lat: float) -> float | None:
        """Marine wave height normalised; None for inland points (no marine data)."""
        payload = await self._get(
            MARINE_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": "wave_height",
                "forecast_days": 3,
                "timezone": "UTC",
            },
            "openmeteo.flood.coastal",
        )
        if payload is None:
            return None
        nums = _floats((payload.get("hourly") or {}).get("wave_height"))
        if not nums:
            return None
        return min(1.0, max(nums) / _WAVE_REF_M)
