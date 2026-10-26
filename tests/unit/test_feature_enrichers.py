"""Gli enricher offline del feature store: pioggia (CERRA) e meteo incendio (#116).

Tutti e due scrivono dentro `training_samples.features`, quindi quello che
conta è cosa **non** scrivono: un campione oltre la copertura CERRA non
riceve una pioggia a zero, un giorno senza osservazione non riceve un FWI
inventato — resta in attesa, e il prossimo giro lo riprova.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from limen.integrations.openmeteo.dtos import WeatherSample
from limen.ml import fire_features, rain_features


class _Conn:
    def __init__(self, pending: list[dict[str, Any]]) -> None:
        self._pending = pending
        self.updates: dict[int, list[str]] = {}

    async def fetch(self, _sql: str) -> list[dict[str, Any]]:
        return self._pending

    async def execute(self, _sql: str, sample_id: int, *payloads: str) -> None:
        self.updates[sample_id] = list(payloads)

    @asynccontextmanager
    async def transaction(self):
        yield


def _use(monkeypatch: pytest.MonkeyPatch, module: Any, conn: _Conn) -> None:
    @asynccontextmanager
    async def _acquire():
        yield conn

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(module, "acquire", _acquire)
    monkeypatch.setattr(module.asyncio, "sleep", _no_sleep)


# ---------------------------------------------------------------------------
# Pioggia
# ---------------------------------------------------------------------------
async def test_rain_enrichment_with_nothing_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, rain_features, _Conn([]))
    assert await rain_features.enrich_rain_features() == 0


async def test_rain_enrichment_writes_aggregates_and_flags_what_it_cannot_fill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tre campioni: uno con la serie, uno il cui nodo torna vuoto (degradato,
    marcato), uno oltre la fine di CERRA (non toccato affatto)."""
    as_of = datetime(2010, 11, 20, 12, tzinfo=UTC)
    conn = _Conn(
        [
            {"id": 1, "cell_id": "a", "valuation_time": as_of, "lon": 16.21, "lat": 40.63},
            {"id": 2, "cell_id": "b", "valuation_time": as_of, "lon": 15.02, "lat": 40.11},
            {
                "id": 3,
                "cell_id": "c",
                "valuation_time": datetime(2024, 1, 1, tzinfo=UTC),
                "lon": 16.2,
                "lat": 40.6,
            },
        ]
    )
    _use(monkeypatch, rain_features, conn)
    calls: list[dict[str, Any]] = []

    class _Client:
        async def get_rainfall_grid(self, *, nodes: list[Any], **kw: Any) -> list[list[Any]]:
            calls.append({"nodes": nodes, **kw})
            wet = [
                WeatherSample(timestamp=as_of - timedelta(hours=h), precipitation_mm=2.0)
                for h in range(1, 49)
            ]
            # I nodi escono ordinati: il primo è quello più a ovest (cella b).
            return [[], wet]

    monkeypatch.setattr(rain_features, "OpenMeteoHttpClient", _Client)

    assert await rain_features.enrich_rain_features(batch_pause_s=0) == 2

    (call,) = calls
    assert call["model"] == "cerra" and call["use_archive"] is True
    assert call["window_start"] == datetime(2010, 10, 21, tzinfo=UTC)
    a = json.loads(conn.updates[1][0])
    b = json.loads(conn.updates[2][0])
    assert a == {
        "rain_24h_mm": 48.0,
        "rain_72h_mm": 96.0,
        "rain_30d_mm": 96.0,
        "max_i_24h_mmh": 2.0,
    }
    assert b["degraded"] == 1.0 and b["rain_72h_mm"] == 0.0
    assert 3 not in conn.updates


# ---------------------------------------------------------------------------
# Meteo incendio
# ---------------------------------------------------------------------------
def _summer(day: datetime, *, days: int) -> list[WeatherSample]:
    return [
        WeatherSample(
            timestamp=day + timedelta(days=d, hours=12),
            precipitation_mm=0.0,
            temperature_c=31.0,
            relative_humidity_pct=25.0,
            wind_speed_kmh=18.0,
        )
        for d in range(days)
    ]


async def test_fire_enrichment_with_nothing_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, fire_features, _Conn([]))
    assert await fire_features.enrich_fire_features() == 0


async def test_fire_enrichment_writes_the_chain_and_leaves_unobserved_days_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fire_day = datetime(2025, 8, 10, 12, tzinfo=UTC)
    gap_day = datetime(2025, 8, 20, 12, tzinfo=UTC)
    conn = _Conn(
        [
            # Due nodi: quello lucano (10, 11) risponde, quello sardo (12) no.
            {"id": 10, "cell_id": "a", "valuation_time": fire_day, "lon": 16.2, "lat": 40.6},
            {"id": 11, "cell_id": "b", "valuation_time": gap_day, "lon": 16.2, "lat": 40.6},
            {"id": 12, "cell_id": "c", "valuation_time": fire_day, "lon": 9.1, "lat": 39.2},
        ]
    )
    _use(monkeypatch, fire_features, conn)

    class _Client:
        async def get_fire_weather_grid(
            self, *, nodes: list[Any], window_start: datetime, **kw: Any
        ):
            out = []
            for lon, _lat in nodes:
                # Il nodo sardo è degradato; quello lucano ha il meteo fino al
                # 15 agosto e poi niente, quindi il 20 non ha osservazione.
                out.append(
                    []
                    if lon < 10
                    else _summer(window_start, days=(fire_day - window_start).days + 6)
                )
            return out

    monkeypatch.setattr(fire_features, "OpenMeteoHttpClient", _Client)

    assert await fire_features.enrich_fire_features(batch_pause_s=0) == 1

    fire_part, rain_part = (json.loads(p) for p in conn.updates[10])
    assert set(fire_part) == {"fwi", "isi", "dc", "chain_days"}
    assert fire_part["fwi"] > 0 and fire_part["chain_days"] > 1
    # Trenta giorni asciutti: la pioggia antecedente è un vero zero, misurato.
    assert rain_part == {"rain_30d_mm": 0.0}
    assert 11 not in conn.updates  # giorno senza osservazione: resta in attesa
    assert 12 not in conn.updates  # nodo degradato: nessun FWI inventato


def test_node_key_is_the_nearest_global_lattice_point() -> None:
    assert fire_features._node_key(16.21, 40.63, spacing=0.1) == (162, 406)
    assert fire_features._node_key(16.26, 40.64, spacing=0.1) == (163, 406)


def _weather(start: datetime, end: datetime) -> list[WeatherSample]:
    """Ore vere fra `start` e `end`, con la pioggia che cambia ogni giorno: la
    catena e la finestra dei trenta giorni hanno qualcosa da portarsi dietro."""
    out = []
    t = start
    while t <= end:
        out.append(
            WeatherSample(
                timestamp=t,
                precipitation_mm=float(t.toordinal() % 7 == 0) * 0.4,
                temperature_c=20.0 + (t.toordinal() % 50) / 5,
                relative_humidity_pct=30.0 + (t.toordinal() % 9),
                wind_speed_kmh=12.0,
            )
        )
        t += timedelta(hours=1)
    return out


def test_walking_the_chain_in_pieces_gives_the_same_numbers() -> None:
    """#327: l'anno dopo riparte dallo stato dell'anno prima, non dal seme."""
    from datetime import date

    from limen.core.models.hazard import HazardType
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds
    from limen.integrations.openmeteo.dtos import MeteoSnapshot

    thresholds = load_hazard_thresholds(HazardType.WILDFIRE)
    days = [date(2023, 11, 1) + timedelta(days=i) for i in range(120)]

    def snap(part: list[Any]) -> MeteoSnapshot:
        start = datetime.combine(part[0], datetime.min.time(), UTC)
        end = datetime.combine(part[-1], datetime.max.time(), UTC)
        return MeteoSnapshot(
            centroid_lon=16.0,
            centroid_lat=40.0,
            window_start=start,
            window_end=end,
            samples=_weather(start - timedelta(days=1), end),
        )

    whole = fire_features.chain_for_days(
        snapshot=snap(days),
        days=days,
        thresholds=thresholds,  # type: ignore[arg-type]
    )
    chain = fire_features.NodeChain(thresholds)  # type: ignore[arg-type]
    pieces: dict[Any, dict[str, float]] = {}
    for part in (days[:45], days[45:46], days[46:]):
        pieces |= chain.walk(snapshot=snap(part), days=part)
    assert pieces == whole


async def test_fire_enrichment_asks_a_year_at_a_time_and_drops_a_broken_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#327: ventiquattro anni in una richiesta andavano in timeout e ogni nodo
    degradava. Ora nessuna finestra supera l'anno; un nodo che smette di
    rispondere tiene quello che ha già scritto e non viene più chiesto."""
    early = datetime(2021, 7, 1, 12, tzinfo=UTC)
    late = datetime(2023, 7, 1, 12, tzinfo=UTC)
    conn = _Conn(
        [
            {"id": 1, "cell_id": "a", "valuation_time": early, "lon": 16.2, "lat": 40.6},
            {"id": 2, "cell_id": "a", "valuation_time": late, "lon": 16.2, "lat": 40.6},
            {"id": 3, "cell_id": "b", "valuation_time": early, "lon": 9.1, "lat": 39.2},
            {"id": 4, "cell_id": "b", "valuation_time": late, "lon": 9.1, "lat": 39.2},
        ]
    )
    _use(monkeypatch, fire_features, conn)
    windows: list[tuple[datetime, datetime, int]] = []

    class _Client:
        async def get_fire_weather_grid(
            self, *, nodes: list[Any], window_start: datetime, window_end: datetime, **kw: Any
        ):
            windows.append((window_start, window_end, len(nodes)))
            # Il nodo sardo risponde solo nel primo blocco.
            return [
                [] if lon < 10 and len(windows) > 1 else _weather(window_start, window_end)
                for lon, _lat in nodes
            ]

    monkeypatch.setattr(fire_features, "OpenMeteoHttpClient", _Client)

    assert await fire_features.enrich_fire_features(batch_pause_s=0) == 3
    assert len(windows) >= 3
    assert all((end - start).days <= fire_features._CHUNK_DAYS + 1 for start, end, _ in windows)
    # Dal terzo blocco in poi si chiede solo il nodo ancora vivo.
    assert [n for *_, n in windows[2:]] == [1] * len(windows[2:])
    assert {1, 2, 3} == set(conn.updates) and 4 not in conn.updates
    # La catena è una sola dal 2021: due anni dopo i giorni di catena lo dicono.
    assert json.loads(conn.updates[2][0])["chain_days"] > 700


def test_mezzogiorno_per_giorno_uguale_alla_serie_intera() -> None:
    """#327: raggruppare le ore per giorno non cambia l'osservazione, pioggia
    delle 24 ore a cavallo della mezzanotte compresa."""
    from datetime import date

    from limen.integrations.openmeteo.dtos import MeteoSnapshot

    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 3, 31, 23, tzinfo=UTC)
    snap = MeteoSnapshot(
        centroid_lon=16.0,
        centroid_lat=40.0,
        window_start=start,
        window_end=end,
        samples=_weather(start, end),
    )
    per_giorno = fire_features._PerGiorno(snap)
    giorni = [date(2024, 1, 1) + timedelta(days=i) for i in range(91)]
    for noon in (11, 12):
        assert [per_giorno.noon_observation(d, noon_hour=noon) for d in giorni] == [
            snap.noon_observation(d, noon_hour=noon) for d in giorni
        ]
