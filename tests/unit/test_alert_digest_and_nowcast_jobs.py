"""Due job event-driven: il digest della coda alert e il trigger radar (#116).

Il digest ha una regola che non si vede dal codice felice: se il messaggio è
già uscito e poi la scrittura dello stato fallisce, il job **non** rilancia —
rilanciare lascerebbe gli aggregati `queued` e li rispedirebbe al giro dopo.

Il trigger radar ha la sua: il radar decide *quando* girare, mai *cosa*
calcolare, e un'AOI che esplode non ferma le altre.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from limen.api.jobs import alert_digest as digest
from limen.api.jobs import nowcast_monitoring as nowcast
from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel
from limen.notifications.governance import ComuneAggregate


def _aggregate(comune: str, hazard: HazardType, level: RiskLevel, score: float) -> ComuneAggregate:
    return ComuneAggregate(
        istat_code=comune[:6],
        comune=comune,
        aoi_id="it-puglia",
        hazard=hazard,
        max_level=level,
        max_score=score,
        cells_count=2,
        top_cells=(("c1", score, level),),
    )


class _Dispatcher:
    def __init__(self) -> None:
        self.payloads: list[Any] = []

    async def dispatch(self, payload: Any) -> dict[str, bool]:
        self.payloads.append(payload)
        return {"telegram": True, "email": False}


def _digest_deps(dispatcher: _Dispatcher | None) -> Any:
    rate_limit = SimpleNamespace(digest_max_age_minutes=360)
    return SimpleNamespace(
        settings=SimpleNamespace(notifications=SimpleNamespace(rate_limit=rate_limit)),
        notification_dispatcher=dispatcher,
    )


def _queue(monkeypatch: pytest.MonkeyPatch, aggregates: list[ComuneAggregate]) -> dict[str, Any]:
    seen: dict[str, Any] = {"expired": 0}

    async def _expire(*, max_age: Any) -> int:
        seen["expired"] += 1
        return 0

    async def _fetch(*, max_age: Any) -> tuple[list[int], list[ComuneAggregate]]:
        return list(range(len(aggregates))), aggregates

    async def _mark(ids: Any, *, digest_id: str, channels: dict[str, bool]) -> int:
        seen["marked"] = (list(ids), digest_id, channels)
        return len(ids)

    async def _record(outcomes: dict[str, bool], *, kind: str, aggregates: int) -> int:
        seen["recorded"] = (outcomes, kind, aggregates)
        return len(outcomes)

    monkeypatch.setattr(digest, "expire_stale", _expire)
    monkeypatch.setattr(digest, "fetch_queued", _fetch)
    monkeypatch.setattr(digest, "mark_sent", _mark)
    monkeypatch.setattr(digest, "record_sends", _record)
    return seen


async def test_empty_queue_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _queue(monkeypatch, [])
    dispatcher = _Dispatcher()
    assert await digest.run_alert_digest(_digest_deps(dispatcher)) == 0
    assert seen["expired"] == 1  # lo scaduto si toglie comunque
    assert dispatcher.payloads == []


async def test_one_message_for_every_queued_comune(monkeypatch: pytest.MonkeyPatch) -> None:
    """Frana e alluvione sullo stesso comune arrivano in un solo messaggio,
    alla classe peggiore fra le due."""
    queue = [
        _aggregate("Taranto", HazardType.LANDSLIDE, RiskLevel.Moderate, 0.45),
        _aggregate("Taranto", HazardType.FLOOD, RiskLevel.High, 0.62),
        _aggregate("Matera", HazardType.LANDSLIDE, RiskLevel.Moderate, 0.41),
    ]
    seen = _queue(monkeypatch, queue)
    dispatcher = _Dispatcher()

    assert await digest.run_alert_digest(_digest_deps(dispatcher)) == 3

    (payload,) = dispatcher.payloads
    assert payload.aoi_id == "italia"
    assert payload.max_level is RiskLevel.High
    assert payload.max_score == pytest.approx(0.62)
    assert "Taranto" in payload.summary_it and "Matera" in payload.summary_it
    ids, digest_id, channels = seen["marked"]
    assert ids == [0, 1, 2]
    assert digest_id.startswith("digest-")
    assert channels == {"telegram": True, "email": False}
    assert seen["recorded"] == ({"telegram": True, "email": False}, "digest", 3)


async def test_without_a_dispatcher_the_queue_is_still_drained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _queue(monkeypatch, [_aggregate("Bari", HazardType.FLOOD, RiskLevel.High, 0.6)])
    assert await digest.run_alert_digest(_digest_deps(None)) == 1
    assert seen["marked"][2] == {}


async def test_a_read_failure_is_logged_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    _queue(monkeypatch, [])

    async def _boom(*, max_age: Any) -> int:
        raise ConnectionError("database giù")

    monkeypatch.setattr(digest, "expire_stale", _boom)
    assert await digest.run_alert_digest(_digest_deps(_Dispatcher())) == 0


async def test_a_persist_failure_after_sending_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Il messaggio è uscito: rilanciare lascerebbe la coda `queued` e lo
    stesso digest partirebbe di nuovo al tick successivo."""
    _queue(monkeypatch, [_aggregate("Bari", HazardType.FLOOD, RiskLevel.High, 0.6)])

    async def _boom(*_a: Any, **_k: Any) -> int:
        raise ConnectionError("database giù")

    monkeypatch.setattr(digest, "mark_sent", _boom)
    dispatcher = _Dispatcher()
    assert await digest.run_alert_digest(_digest_deps(dispatcher)) == 1
    assert len(dispatcher.payloads) == 1


# ---------------------------------------------------------------------------
# Trigger radar
# ---------------------------------------------------------------------------
_BBOXES = {
    "it-basilicata": (15.3, 39.9, 16.9, 41.1),
    "it-molise": (13.9, 41.3, 15.2, 42.1),
    "it-puglia": (14.9, 39.7, 18.6, 42.3),
    "it-sardegna": (8.1, 38.8, 9.9, 41.3),
}


class _Sri:
    time = datetime(2026, 9, 15, 14, 5, tzinfo=UTC)

    def __init__(self, by_bbox: dict[tuple[float, ...], tuple[float, int]]) -> None:
        self._by_bbox = by_bbox

    def peak(self, bbox: tuple[float, ...], *, threshold: float) -> tuple[float, int]:
        return self._by_bbox.get(bbox, (0.0, 0))


class _Workflow:
    def __init__(self, fail_on: str | None) -> None:
        self._fail_on = fail_on
        self.ran: list[str] = []

    async def run(self, ctx: Any) -> Any:
        if ctx.aoi_id == self._fail_on:
            raise RuntimeError("open-meteo giù")
        self.ran.append(ctx.aoi_id)
        return SimpleNamespace(
            context=SimpleNamespace(cell_results=[1, 2, 3], assessment_id=9, assessment=None),
            nodes=[],
        )


def _nowcast(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sri: _Sri | None,
    fresh: frozenset[str] = frozenset(),
    fail_on: str | None = None,
) -> tuple[Any, _Workflow, list[str], list[dict[str, Any]]]:
    async def _series(_step: Any, _count: int) -> list[_Sri]:
        return [] if sri is None else [sri]

    salvati: list[float] = []

    async def _salva(_serie: list[Any], soglia: float) -> None:
        salvati.append(soglia)

    class _Conn:
        async def fetch(self, _sql: str) -> list[dict[str, Any]]:
            return [
                {"id": k, "x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3]}
                for k, b in sorted(_BBOXES.items())
            ]

    @asynccontextmanager
    async def _acquire():
        yield _Conn()

    async def _assessed_within(aoi_id: str, *, minutes: int) -> bool:
        return aoi_id in fresh

    profiles: list[str] = []
    workflow = _Workflow(fail_on)

    def _build(*, profile: str) -> _Workflow:
        profiles.append(profile)
        return workflow

    tracked_rows: list[dict[str, Any]] = []

    @asynccontextmanager
    async def _tracked(_job: str, *, scope: str | None = None):
        metrics: dict[str, Any] = {"scope": scope}
        yield metrics
        tracked_rows.append(metrics)

    monkeypatch.setattr(nowcast, "get_sri_series", _series)
    monkeypatch.setattr(nowcast, "_salva_temporali", _salva)
    monkeypatch.setattr(nowcast, "acquire", _acquire)
    monkeypatch.setattr(nowcast, "assessed_within", _assessed_within)
    monkeypatch.setattr(nowcast, "tracked", _tracked)
    deps = SimpleNamespace(
        settings=SimpleNamespace(
            nowcast=SimpleNamespace(
                min_intensity_mmh=30.0,
                min_pixels=3,
                cooldown_minutes=45,
                storm_mmh=10.0,
                bias_correction=False,
            ),
            enable_insitu=False,
        ),
        build_workflow=_build,
    )
    return deps, workflow, profiles, tracked_rows


async def test_no_radar_frame_triggers_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    deps, workflow, _, _ = _nowcast(monkeypatch, sri=None)
    assert await nowcast.run_nowcast_monitoring(deps) == {}
    assert workflow.ran == []


async def test_radar_triggers_only_real_storms_outside_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Basilicata: temporale vero. Molise: un pixel caldo solo, clutter.
    Puglia: pioggia sotto soglia. Sardegna: temporale, ma già valutata da poco."""
    sri = _Sri(
        {
            _BBOXES["it-basilicata"]: (52.34, 12),
            _BBOXES["it-molise"]: (80.0, 1),
            _BBOXES["it-puglia"]: (18.0, 40),
            _BBOXES["it-sardegna"]: (45.0, 9),
        }
    )
    deps, workflow, profiles, rows = _nowcast(
        monkeypatch, sri=sri, fresh=frozenset({"it-sardegna"})
    )

    triggered = await nowcast.run_nowcast_monitoring(deps)

    assert triggered == {"it-basilicata": 52.3}
    assert workflow.ran == ["it-basilicata"]
    # Profilo orario: nessun LLM sincrono dentro un tick event-driven (#78).
    assert profiles == ["hourly"]
    assert rows[0]["scope"] == "it-basilicata"
    assert rows[0]["cells"] == 3


async def test_a_failing_aoi_does_not_stop_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    sri = _Sri({_BBOXES["it-basilicata"]: (40.0, 5), _BBOXES["it-molise"]: (35.0, 4)})
    deps, workflow, _, _ = _nowcast(monkeypatch, sri=sri, fail_on="it-basilicata")

    triggered = await nowcast.run_nowcast_monitoring(deps)

    assert triggered == {"it-molise": 35.0}
    assert workflow.ran == ["it-molise"]


async def test_i_temporali_si_salvano_e_un_errore_non_ferma_la_sveglia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#643: i temporali vanno nella tabella dell'API; se la scrittura fallisce
    la sveglia prosegue e scatta lo stesso."""
    import numpy as np
    from dpc_radar import RainGrid, product
    from rasterio import Affine
    from rasterio.crs import CRS

    data = np.zeros((40, 40))
    data[10:16, 10:16] = 25.0
    griglia = RainGrid(
        product("SRI"),
        datetime(2026, 9, 15, 14, 5, tzinfo=UTC),
        data,
        Affine(1000.0, 0, 500000.0, 0, -1000.0, 4600000.0),
        CRS.from_epsg(32633),
    )
    scritti: list[Any] = []

    async def _sostituisci(t: list[Any]) -> None:
        scritti.extend(t)

    monkeypatch.setattr(nowcast.radar_temporali_repo, "sostituisci", _sostituisci)
    await nowcast._salva_temporali([griglia], 10.0)
    [t] = scritti
    assert t.picco_mmh == 25.0 and t.area_km2 == 36.0
    assert t.velocita_kmh is None  # un fotogramma solo: il moto non si sa

    async def _rotto(_t: list[Any]) -> None:
        raise RuntimeError("db giù")

    monkeypatch.setattr(nowcast.radar_temporali_repo, "sostituisci", _rotto)
    await nowcast._salva_temporali([griglia], 10.0)


def test_il_temporale_va_dove_dice_il_moto() -> None:
    from limen.data.repos.radar_temporali_repo import Temporale
    from limen.integrations.dpc.temporali import fra_un_ora, geojson

    t = Temporale(
        datetime(2026, 11, 19, 9, 30, tzinfo=UTC),
        0,
        10.0,
        12.0,
        42.0,
        36.0,
        42.5,
        30.0,
        12.0,
        42.0,
        (11.9, 41.9, 12.1, 42.1),
        30.0,
        90.0,
    )
    lon, lat = fra_un_ora(t) or (0.0, 0.0)
    assert lat == pytest.approx(42.0) and lon == pytest.approx(12.0 + 30 / (111.2 * 0.7431), 1e-3)
    fc = geojson([t, replace(t, n=1, velocita_kmh=None, direzione_gradi=None)])
    assert [f["geometry"]["type"] for f in fc["features"]] == ["Point", "LineString", "Point"]
