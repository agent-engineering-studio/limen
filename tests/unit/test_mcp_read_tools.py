"""Strumenti MCP di sola lettura: la forma della risposta, senza database (#116).

Il SQL di questi strumenti è esercitato dai test d'integrazione. Qui si prova
quello che un agente legge davvero e che si rompe in silenzio: arrotondamenti,
date in ISO, limiti fissati ai bordi, il rifiuto di un pericolo che la
superficie non sa servire, e il report nazionale che mette insieme tutto.

La connessione è finta e risponde in base a un frammento della query: così
ogni strumento riceve le righe che si aspetta senza che il test debba
conoscerne l'ordine di chiamata.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from limen.core.models.hazard import HazardType
from limen.mcp import tools

T = datetime(2026, 9, 15, 6, tzinfo=UTC)


class _Conn:
    """Risponde a `fetch`/`fetchrow`/`fetchval` scegliendo per frammento di SQL."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self._routes = routes
        self.seen: list[tuple[str, tuple[Any, ...]]] = []

    def _answer(self, sql: str, args: tuple[Any, ...]) -> Any:
        self.seen.append((sql, args))
        for fragment, answer in self._routes.items():
            if fragment in sql:
                return answer(args) if callable(answer) else answer
        raise AssertionError(f"query non prevista dal test: {sql[:80]!r}")

    async def fetch(self, sql: str, *args: Any) -> Any:
        return self._answer(sql, args)

    async def fetchrow(self, sql: str, *args: Any) -> Any:
        return self._answer(sql, args)

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return self._answer(sql, args)


def _use(monkeypatch: pytest.MonkeyPatch, conn: _Conn) -> None:
    @asynccontextmanager
    async def _acquire():
        yield conn

    monkeypatch.setattr(tools, "acquire", _acquire)


_SUMMARY_ROWS = [
    {
        "aoi_id": "it-puglia",
        "computed_at": T,
        "cells": 100,
        "max_score": 0.87654,
        "high_or_above": 3,
        "moderate": 7,
    }
]
_TOP_ROWS = [
    {"cell_id": "c1", "aoi_id": "it-puglia", "score": 0.87654, "class": "High", "computed_at": T}
]


# ---------------------------------------------------------------------------
# Validazione ai bordi
# ---------------------------------------------------------------------------
def test_unknown_hazard_names_the_valid_ones() -> None:
    with pytest.raises(ValueError, match="known:"):
        tools._coerce_hazard("terremoto")
    assert tools._coerce_hazard(None) is HazardType.LANDSLIDE


def test_comune_surfaces_refuse_a_hazard_they_cannot_serve() -> None:
    """La vista comunale è fissata alle frane: ignorare in silenzio un altro
    pericolo farebbe credere a un agente di avere numeri sull'alluvione."""
    with pytest.raises(ValueError, match="landslide-only"):
        tools._require_default_hazard("flood", "top_comuni")


def test_coerce_json_tolerates_strings_garbage_and_lists() -> None:
    assert tools._coerce_json({"a": 1}) == {"a": 1}
    assert tools._coerce_json('{"a": 1}') == {"a": 1}
    assert tools._coerce_json("[1, 2]") == {}
    assert tools._coerce_json("{rotto") == {}
    assert tools._coerce_json(None) == {}


# ---------------------------------------------------------------------------
# Letture
# ---------------------------------------------------------------------------
async def test_risk_summary_rounds_and_serialises(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn({"GROUP BY aoi_id": _SUMMARY_ROWS})
    _use(monkeypatch, conn)
    out = await tools.risk_summary()
    assert out == [
        {
            "aoi_id": "it-puglia",
            "computed_at": T.isoformat(),
            "cells_scored": 100,
            "max_score": 0.877,
            "high_or_above": 3,
            "moderate": 7,
        }
    ]
    # Il pericolo di default arriva alla query anche se non richiesto.
    assert conn.seen[0][1][1] == "landslide"


async def test_top_risk_cells_clamps_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un agente che chiede 10.000 celle ne riceve al più 100, e chi chiede 0
    ne riceve una: il limite protegge il database e il contesto dell'agente."""
    conn = _Conn({"ORDER BY risk_score DESC": _TOP_ROWS})
    _use(monkeypatch, conn)
    out = await tools.top_risk_cells(limit=10_000)
    assert conn.seen[-1][1][0] == 100
    assert out[0]["score"] == 0.877
    await tools.top_risk_cells(limit=0)
    assert conn.seen[-1][1][0] == 1


async def test_cell_breakdown_found_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {
        "cell_id": "c1",
        "computed_at": T,
        "score": 0.5,
        "class": "Moderate",
        "factors": '{"s": 0.2}',
        "explanation": {"briefing_it": "testo"},
    }
    _use(monkeypatch, _Conn({"LIMIT 1": row}))
    out = await tools.cell_breakdown("c1")
    assert out["factors"] == {"s": 0.2}
    assert out["explanation"] == {"briefing_it": "testo"}

    _use(monkeypatch, _Conn({"LIMIT 1": None}))
    assert "error" in await tools.cell_breakdown("sconosciuta")


async def test_recent_alerts_falls_back_on_a_bad_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una soglia sconosciuta diventa Moderate — e l'elenco dei livelli
    passati alla query parte da lì — invece di una query con un valore che
    Postgres rifiuterebbe."""
    rows = [{"cell_id": "c1", "aoi_id": "it-x", "score": 0.9, "class": "High", "computed_at": T}]
    conn = _Conn({"ra.class = ANY": rows})
    _use(monkeypatch, conn)
    out = await tools.recent_alerts(threshold="apocalittico", since_hours=99_999, limit=-5)
    levels, since, limit, hazard = conn.seen[0][1]
    assert levels == ["Moderate", "High", "VeryHigh"]
    assert since == 24 * 30  # al massimo un mese
    assert limit == 1
    assert hazard == "landslide"
    assert out[0]["level"] == "High"


async def test_multi_hazard_summary_for_a_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    per_hazard = [
        {"hazard_type": "flood", "risk_score": None, "risk_level": None, "computed_at": None},
        {"hazard_type": "landslide", "risk_score": 0.61234, "risk_level": "High", "computed_at": T},
    ]
    worst = {
        "aoi_id": "it-x",
        "worst_hazard": "landslide",
        "worst_level": "High",
        "worst_score": 0.61,
        "hazards_at_moderate": ["landslide"],
        "hazards_at_high": None,
    }
    _use(
        monkeypatch,
        _Conn(
            {
                "WHERE cell_id = $1\n                ORDER BY": per_hazard,
                "v_multi_hazard WHERE cell_id": worst,
            }
        ),
    )
    out = await tools.multi_hazard_summary(cell_id="c1")
    assert out["scope"] == "cell"
    assert out["worst_hazard"] == "landslide"
    assert out["hazards_at_high"] == []
    # Un pericolo non ancora valutato resta visibile, con valori nulli.
    assert out["per_hazard"][0] == {
        "hazard": "flood",
        "score": None,
        "level": None,
        "computed_at": None,
    }


async def test_multi_hazard_summary_rejects_an_unknown_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, _Conn({"ORDER BY hazard_type": [], "v_multi_hazard WHERE cell_id": None}))
    with pytest.raises(ValueError, match="sconosciuta"):
        await tools.multi_hazard_summary(cell_id="zz")


async def test_multi_hazard_summary_for_an_aoi(monkeypatch: pytest.MonkeyPatch) -> None:
    agg = [
        {
            "hazard_type": "landslide",
            "cells_scored": 10,
            "max_score": 0.4,
            "high_or_above": 0,
            "moderate": 2,
            "computed_at": T,
        }
    ]
    _use(monkeypatch, _Conn({"GROUP BY hazard_type": agg, "array_length": 3}))
    out = await tools.multi_hazard_summary(aoi_id="it-x")
    assert out["cells_multi_hazard_high"] == 3
    assert out["per_hazard"][0]["moderate"] == 2


async def test_multi_hazard_summary_needs_a_scope() -> None:
    with pytest.raises(ValueError):
        await tools.multi_hazard_summary()


# ---------------------------------------------------------------------------
# Report nazionale
# ---------------------------------------------------------------------------
async def test_national_report_assembles_totals_places_and_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ml = [{"cell_id": "c9", "aoi_id": "it-puglia", "probability": 0.33333, "risk_class": "Low"}]
    points = [
        {"id": "c1", "lon": 16.0, "lat": 41.0},
        {"id": "c9", "lon": 16.5, "lat": 41.5},
    ]
    # I frammenti piu' specifici prima: la query su `model_runs` contiene
    # `GROUP BY aoi_id` nella sua CTE, e con l'ordine inverso riceverebbe le
    # righe del riepilogo regionale.
    routes = {
        "FROM model_runs": ml,
        "GROUP BY aoi_id": _SUMMARY_ROWS,
        "ORDER BY risk_score DESC": _TOP_ROWS,
        "alert_dispatches": 4,
        "forecast_dispatches": None,
        "ST_Centroid": points,
    }
    _use(monkeypatch, _Conn(routes))

    async def _places(pts: list[tuple[float, float]]) -> list[str | None]:
        return ["Bari" if lon == 16.0 else None for lon, _lat in pts]

    async def _scorable() -> list[tuple[HazardType, str]]:
        return [(HazardType.LANDSLIDE, "Frane")]

    async def _no_cascades() -> dict[str, Any]:
        return {}

    import limen.data.repos.hazards_repo as hazards_repo
    import limen.integrations.geoserver_source.comuni as comuni

    monkeypatch.setattr(comuni, "comuni_for_points", _places)
    monkeypatch.setattr(hazards_repo, "scorable_with_labels", _scorable)
    monkeypatch.setattr(tools, "active_cascades", _no_cascades)

    report = await tools.national_report()

    assert report["totals"] == {"regions": 1, "cells": 100, "high_or_above": 3, "moderate": 7}
    assert report["top_cells"][0]["place"] == "Bari"
    assert report["ml_top_cells"][0]["probability"] == 0.333
    assert report["alerts_24h"] == 4
    assert report["forecast_alerts_24h"] == 0  # None dal DB diventa zero
    assert report["hazards"][0]["label_it"] == "Frane"
    assert isinstance(report["report_it"], str) and report["report_it"]


# ---------------------------------------------------------------------------
# Rendering italiano
# ---------------------------------------------------------------------------
def test_hazard_sections_are_silent_with_a_single_hazard() -> None:
    """Con un solo pericolo le sezioni ripeterebbero il paragrafo principale."""
    assert tools._render_hazard_sections_it({"hazards": [{"totals": {}}]}) == []


def test_hazard_sections_name_the_worst_point_only_when_it_matters() -> None:
    report = {
        "hazards": [
            {
                "label_it": "Frane",
                "totals": {"cells": 10, "high_or_above": 2, "moderate": 1},
                "top_cells": [{"level": "High", "place": "Potenza", "score": 0.81}],
            },
            {
                "label_it": "Alluvione",
                "totals": {"cells": 10, "high_or_above": 0, "moderate": 0},
                "top_cells": [{"level": "Low", "place": "Matera", "score": 0.1}],
            },
            {
                "label_it": "Incendio",
                "totals": {"cells": 0, "high_or_above": 0, "moderate": 0},
                "top_cells": [],
            },
        ]
    }
    text = "\n".join(tools._render_hazard_sections_it(report))
    assert "Potenza (0.81)" in text
    # A rischio basso il massimo di una lista tranquilla non si nomina: letto
    # accanto a un nome di paese sembrerebbe un avviso.
    assert "Matera" not in text
    assert "nessuna zona sopra il livello basso" in text
    assert "incendio: nessuna valutazione disponibile" in text


def test_cascade_section_describes_both_rules() -> None:
    report = {
        "cascades": {
            "post_fire_flood": {"cells": 5, "window_months": 24, "max_multiplier": 1.5},
            "joint_rain": {
                "cells": 2,
                "top_cells": [{"hazards": ["flood", "landslide"]}],
            },
        }
    }
    text = "\n".join(tools._render_cascade_section_it(report))
    assert "5 aree bruciate" in text
    assert "flood e landslide" in text
    assert tools._render_cascade_section_it({"cascades": {}}) == []


# ---------------------------------------------------------------------------
# Strumenti amministrativi: il lavoro vero sta altrove, qui il cablaggio
# ---------------------------------------------------------------------------
@pytest.fixture()
def _admin(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv(tools.ADMIN_TOKEN_ENV, "segreto")
    return "segreto"


async def test_run_monitor_reports_what_the_workflow_did(
    monkeypatch: pytest.MonkeyPatch, _admin: str
) -> None:
    class _Assessment:
        cells_high_or_above = 2

    class _Ctx:
        assessment_id = 99
        cell_results = (object(), object(), object())
        assessment = _Assessment()
        dispatched_alerts = ("c1",)

    class _Result:
        context = _Ctx()

    class _Workflow:
        async def run(self, _ctx: Any) -> _Result:
            return _Result()

    import limen.agents.workflows.main_workflow as wf

    monkeypatch.setattr(wf, "build_hazard_workflow", lambda _hz, **_k: _Workflow())
    out = await tools.run_monitor("it-puglia", admin_token=_admin, hazard="flood")
    assert out == {
        "aoi_id": "it-puglia",
        "hazard": "flood",
        "assessment_id": 99,
        "cells_scored": 3,
        "high_or_above": 2,
        "dispatched_alerts": ["c1"],
    }


async def test_build_static_report_reports_a_skip(
    monkeypatch: pytest.MonkeyPatch, _admin: str
) -> None:
    import limen.report.builder as builder

    async def _skip(_settings: Any) -> None:
        return None

    monkeypatch.setattr(builder, "build_report", _skip)
    assert await tools.build_static_report(admin_token=_admin) == {"build": None, "skipped": True}


async def test_run_forecast_history_passes_the_hazard(
    monkeypatch: pytest.MonkeyPatch, _admin: str
) -> None:
    import limen.agents.workflows.forecast_history as fh

    seen: dict[str, Any] = {}

    async def _run(*, aoi_ids: Any, hazard: HazardType) -> int:
        seen.update(aoi_ids=aoi_ids, hazard=hazard)
        return 12

    monkeypatch.setattr(fh, "run_forecast_history", _run)
    out = await tools.run_forecast_history(admin_token=_admin, aoi_ids=["it-x"], hazard="wildfire")
    assert out == {"cells_persisted": 12, "aoi_ids": ["it-x"], "hazard": "wildfire"}
    assert seen["hazard"] is HazardType.WILDFIRE


async def test_comune_tools_delegate_to_the_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    import limen.data.repos.comune_risk as comune_risk

    async def _detail(code: str) -> dict[str, Any] | None:
        return {"comune": {"istat": code}} if code == "072006" else None

    async def _top(*, aoi_id: str | None, limit: int) -> list[dict[str, Any]]:
        return [{"aoi_id": aoi_id, "limit": limit}]

    monkeypatch.setattr(comune_risk, "comune_detail", _detail)
    monkeypatch.setattr(comune_risk, "top_comuni", _top)

    assert await tools.comune_risk("072006") == {"istat": "072006"}
    assert "error" in await tools.comune_risk("000000")
    assert await tools.top_comuni(limit=3, aoi_id="it-puglia") == [
        {"aoi_id": "it-puglia", "limit": 3}
    ]


async def test_hazards_lists_the_scorable_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    import limen.data.repos.hazards_repo as hazards_repo

    async def _scorable() -> list[tuple[HazardType, str]]:
        return [(HazardType.LANDSLIDE, "Frane"), (HazardType.FLOOD, "Alluvioni")]

    monkeypatch.setattr(hazards_repo, "scorable_with_labels", _scorable)
    out = await tools.hazards()
    assert out["default"] == "landslide"
    assert [h["hazard"] for h in out["items"]] == ["landslide", "flood"]
