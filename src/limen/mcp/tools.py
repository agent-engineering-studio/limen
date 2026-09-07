"""``limen-ops`` MCP tool bodies — plain async functions, no FastMCP here.

Read tools are thin queries over the operational tables (same SQL shapes as
the public API endpoints). The one mutating tool (``run_monitor``) is gated
by ``MCP_ADMIN_TOKEN`` exactly like the geodata MCP's ``refresh``: env var
unset ⇒ disabled (fail-closed).

Everything here is advisory/operator tooling: nothing participates in the
hourly scoring critical path, and nothing can alter a persisted score.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire

log = get_logger(__name__)

ADMIN_TOKEN_ENV = "MCP_ADMIN_TOKEN"

_LEVELS = ("None", "Low", "Moderate", "High", "VeryHigh")


class AdminAuthError(Exception):
    """Raised when a mutating tool is called without a valid admin token."""


def check_admin_token(token: str | None) -> None:
    """Fail-closed gate: env unset ⇒ always denied."""
    expected = os.environ.get(ADMIN_TOKEN_ENV, "").strip()
    if not expected:
        raise AdminAuthError(
            f"mutating tools are disabled: {ADMIN_TOKEN_ENV} is not set on the server"
        )
    if not token or token != expected:
        raise AdminAuthError("invalid admin token")


def _coerce_hazard(value: str | None) -> HazardType:
    """Parse an agent-supplied hazard name.

    A tool boundary faces the outside, so validating here is right: an
    unknown name must say what is valid rather than silently score
    landslides and report them as something else.
    """
    if value is None:
        return DEFAULT_HAZARD
    try:
        return HazardType(value)
    except ValueError:
        known = ", ".join(h.value for h in HazardType)
        raise ValueError(f"unknown hazard {value!r}; known: {known}") from None


def _require_default_hazard(hazard: str | None, surface: str) -> HazardType:
    """Accept the parameter, refuse a value the surface cannot honour.

    ``mv_comune_risk`` is pinned to the default hazard in SQL (migration 028),
    because its ``exposure_rank`` reads a component key only the landslide
    breakdown has. Silently ignoring a different value would let an agent
    believe it got flood numbers, which is worse than saying no.
    """
    hz = _coerce_hazard(hazard)
    if hz is not DEFAULT_HAZARD:
        raise ValueError(
            f"{surface} is {DEFAULT_HAZARD.value}-only: the comune rollup view is "
            f"pinned to it until Fase 2 gives each hazard its own exposure term"
        )
    return hz


def _coerce_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            out = json.loads(value)
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def risk_summary(
    aoi_id: str | None = None, hazard: str | None = None
) -> list[dict[str, Any]]:
    """Latest assessment summary per AOI: when, cells per level, max score."""
    # mv_latest_risk (latest assessment per cell, tile pipeline) — the raw
    # risk_assessments table grows by millions of rows/day nationally and
    # latest-per-AOI scans over it time out.
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT aoi_id, MAX(computed_at) AS computed_at,
                   COUNT(*) AS cells,
                   MAX(risk_score) AS max_score,
                   COUNT(*) FILTER (WHERE risk_level IN ('High','VeryHigh')) AS high_or_above,
                   COUNT(*) FILTER (WHERE risk_level = 'Moderate') AS moderate
            FROM mv_latest_risk
            WHERE risk_score IS NOT NULL
              AND hazard_type = $2
              AND ($1::text IS NULL OR aoi_id = $1)
            GROUP BY aoi_id
            ORDER BY high_or_above DESC, max_score DESC, aoi_id
            """,
            aoi_id,
            _coerce_hazard(hazard).value,
        )
    return [
        {
            "aoi_id": str(r["aoi_id"]),
            "computed_at": r["computed_at"].isoformat(),
            "cells_scored": int(r["cells"]),
            "max_score": round(float(r["max_score"]), 3),
            "high_or_above": int(r["high_or_above"]),
            "moderate": int(r["moderate"]),
        }
        for r in rows
    ]


async def top_risk_cells(
    limit: int = 10, aoi_id: str | None = None, hazard: str | None = None
) -> list[dict[str, Any]]:
    """Highest-scoring cells from each AOI's latest assessment (national ranking)."""
    limit = max(1, min(int(limit), 100))
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cell_id, aoi_id, risk_score AS score,
                   risk_level AS class, computed_at
            FROM mv_latest_risk
            WHERE risk_score IS NOT NULL
              AND hazard_type = $3
              AND ($2::text IS NULL OR aoi_id = $2)
            -- cell_id spareggia: senza di esso una griglia con molte celle
            -- allo stesso punteggio (lo scenario normale in un giorno
            -- tranquillo) restituisce N righe arbitrarie, e un agente che
            -- ripete la domanda ottiene una risposta diversa senza motivo.
            ORDER BY risk_score DESC, cell_id
            LIMIT $1
            """,
            limit,
            aoi_id,
            _coerce_hazard(hazard).value,
        )
    return [
        {
            "cell_id": str(r["cell_id"]),
            "aoi_id": str(r["aoi_id"]),
            "score": round(float(r["score"]), 3),
            "level": str(r["class"]),
            "computed_at": r["computed_at"].isoformat(),
        }
        for r in rows
    ]


async def cell_breakdown(cell_id: str, hazard: str | None = None) -> dict[str, Any]:
    """Latest persisted per-component breakdown + briefing for one cell."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cell_id, computed_at, score, class, factors, explanation
            FROM risk_assessments
            WHERE cell_id = $1 AND hazard_type = $2
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            cell_id,
            _coerce_hazard(hazard).value,
        )
    if row is None:
        return {"error": f"no assessment for cell {cell_id!r}"}
    return {
        "cell_id": str(row["cell_id"]),
        "computed_at": row["computed_at"].isoformat(),
        "score": round(float(row["score"]), 3),
        "level": str(row["class"]),
        "factors": _coerce_json(row["factors"]),
        "explanation": _coerce_json(row["explanation"]),
    }


async def recent_alerts(
    threshold: str = "Moderate",
    since_hours: int = 24,
    limit: int = 50,
    hazard: str | None = None,
) -> list[dict[str, Any]]:
    """Cells at/above ``threshold`` in the last ``since_hours`` hours."""
    if threshold not in _LEVELS:
        threshold = "Moderate"
    levels = list(_LEVELS[_LEVELS.index(threshold) :])
    since_hours = max(1, min(int(since_hours), 24 * 30))
    limit = max(1, min(int(limit), 500))
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ra.cell_id, g.aoi_id, ra.score, ra.class, ra.computed_at
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE ra.class = ANY($1::text[])
              AND ra.hazard_type = $4
              AND ra.computed_at >= now() - ($2::int * interval '1 hour')
            ORDER BY ra.computed_at DESC, ra.score DESC
            LIMIT $3
            """,
            levels,
            since_hours,
            limit,
            _coerce_hazard(hazard).value,
        )
    return [
        {
            "cell_id": str(r["cell_id"]),
            "aoi_id": str(r["aoi_id"]),
            "score": round(float(r["score"]), 3),
            "level": str(r["class"]),
            "computed_at": r["computed_at"].isoformat(),
        }
        for r in rows
    ]


async def run_monitor(
    aoi_id: str,
    admin_token: str | None = None,
    cell_limit: int | None = None,
    hazard: str | None = None,
) -> dict[str, Any]:
    """Run the full MAF workflow once for ``aoi_id`` (admin only).

    ``hazard`` selects which danger to score. An unscorable one raises at
    build time with a message naming what is missing.
    """
    check_admin_token(admin_token)
    from limen.agents.workflows.main_workflow import build_hazard_workflow
    from limen.core.models.context import MonitoringContext

    hz = _coerce_hazard(hazard)
    workflow = build_hazard_workflow(hz, cell_limit=cell_limit)
    ctx = MonitoringContext(aoi_id=aoi_id, hazard_type=hz, valuation_time=datetime.now(UTC))
    result = await workflow.run(ctx)
    out = result.context
    log.info(
        "mcp.run_monitor.done",
        aoi_id=aoi_id,
        hazard=hz.value,
        cells=len(out.cell_results),
    )
    return {
        "aoi_id": aoi_id,
        "hazard": hz.value,
        "assessment_id": out.assessment_id,
        "cells_scored": len(out.cell_results),
        "high_or_above": out.assessment.cells_high_or_above if out.assessment else 0,
        "dispatched_alerts": list(out.dispatched_alerts),
    }


async def build_static_report(admin_token: str | None = None) -> dict[str, Any]:
    """Generate the static HTML risk report once (idempotent). Admin only.

    Wraps ``limen report build``: the recurring generation is already handled
    by Limen's APScheduler (JOB_DAILY_REPORT / JOB_HTML_REPORT); this tool lets
    an agent trigger an on-demand build. Returns the archive path, or a skip
    when the assessment signature is unchanged.
    """
    check_admin_token(admin_token)
    from limen.config.settings import get_settings
    from limen.integrations._http import SharedHttpClient
    from limen.report.builder import build_report as _build

    try:
        result = await _build(get_settings())
    finally:
        await SharedHttpClient.aclose()
    log.info("mcp.build_report.done", build=str(result) if result is not None else "skipped")
    return {"build": str(result) if result is not None else None, "skipped": result is None}


async def run_forecast_history(
    admin_token: str | None = None,
    aoi_ids: list[str] | None = None,
    hazard: str | None = None,
) -> dict[str, Any]:
    """Persist the per-cell forecast trend (+24/48/72h, ≥Moderate). Admin only.

    Wraps ``limen forecast-history`` so the sidebar / report trend can be
    refreshed on demand. ``aoi_ids`` omitted ⇒ every seeded AOI.
    """
    check_admin_token(admin_token)
    from limen.agents.workflows.forecast_history import (
        run_forecast_history as _run,
    )

    hz = _coerce_hazard(hazard)
    total = await _run(aoi_ids=aoi_ids, hazard=hz)
    log.info("mcp.forecast_history.done", cells=total, hazard=hz.value, aois=aoi_ids or "all")
    return {"cells_persisted": total, "aoi_ids": aoi_ids, "hazard": hz.value}


async def comune_risk(istat_code: str, hazard: str | None = None) -> dict[str, Any]:
    """Comune rollup (worst class, counts, exposure) for one ISTAT code."""
    from limen.data.repos.comune_risk import comune_detail

    _require_default_hazard(hazard, "comune_risk")
    detail = await comune_detail(istat_code)
    return detail["comune"] if detail else {"error": f"comune {istat_code!r} not found"}


async def top_comuni(
    limit: int = 10, aoi_id: str | None = None, hazard: str | None = None
) -> list[dict[str, Any]]:
    """Comuni with alerting cells, ranked by exposure (national or per-AOI)."""
    from limen.data.repos.comune_risk import top_comuni as _top

    _require_default_hazard(hazard, "top_comuni")
    return await _top(aoi_id=aoi_id, limit=limit)


async def hazards() -> dict[str, Any]:
    """Hazards this deployment can score, with their Italian labels."""
    from limen.data.repos.hazards_repo import scorable_with_labels

    return {
        "items": [
            {"hazard": h.value, "label_it": label} for h, label in await scorable_with_labels()
        ],
        "default": DEFAULT_HAZARD.value,
    }


async def national_report(hazard: str | None = None) -> dict[str, Any]:
    """Aggregate national picture: regions, top cells, ML shadow, 24h alerts.

    One hazard leads — ``hazard`` picks it, the default leads when omitted —
    and the payload keeps the shape it had when landslide was the only one, so
    a client that predates the hazard dimension reads it unchanged. Two
    sections are added on top (#58): ``hazards``, one block per hazard this
    deployment can score, and ``cascades``, the cross-hazard rules currently
    firing. Both are additive: nothing that existed moved.
    """
    hz = _coerce_hazard(hazard)
    regions = await risk_summary(hazard=hz.value)
    top = await top_risk_cells(limit=10, hazard=hz.value)
    async with acquire() as conn:
        ml_rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT aoi_id, MAX(computed_at) AS ts
                FROM model_runs WHERE hazard_type = $1 GROUP BY aoi_id
            )
            SELECT m.cell_id, m.aoi_id, m.probability, m.risk_class
            FROM model_runs m
            JOIN latest l ON l.aoi_id = m.aoi_id AND l.ts = m.computed_at
            WHERE m.hazard_type = $1
            ORDER BY m.probability DESC
            LIMIT 10
            """,
            hz.value,
        )
        alerts_24h = await conn.fetchval(
            """SELECT COUNT(*) FROM alert_dispatches
               WHERE dispatched_at >= now() - interval '24 hours'
                 AND hazard_type = $1""",
            hz.value,
        )
        forecast_24h = await conn.fetchval(
            """SELECT COUNT(*) FROM forecast_dispatches
               WHERE dispatched_at >= now() - interval '24 hours'
                 AND hazard_type = $1""",
            hz.value,
        )
    from limen.integrations.geoserver_source.comuni import comuni_for_points

    async def _places(cell_ids: list[str]) -> list[str | None]:
        if not cell_ids:
            return []
        async with acquire() as conn:
            pts = await conn.fetch(
                """
                SELECT id, ST_X(ST_Centroid(geom)) AS lon,
                       ST_Y(ST_Centroid(geom)) AS lat
                FROM grid_cells WHERE id = ANY($1::text[])
                """,
                cell_ids,
            )
        by_id = {str(r["id"]): (float(r["lon"]), float(r["lat"])) for r in pts}
        ordered = [by_id.get(c, (0.0, 0.0)) for c in cell_ids]
        return await comuni_for_points(ordered)

    top_places = await _places([c["cell_id"] for c in top])
    for c, place in zip(top, top_places, strict=True):
        c["place"] = place
    ml_cells = [str(r["cell_id"]) for r in ml_rows]
    ml_places = await _places(ml_cells)

    per_hazard = await _per_hazard_blocks(_places)
    cascades = await active_cascades()

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "hazard": hz.value,
        "regions": regions,
        "totals": {
            "regions": len(regions),
            "cells": sum(r["cells_scored"] for r in regions),
            "high_or_above": sum(r["high_or_above"] for r in regions),
            "moderate": sum(r["moderate"] for r in regions),
        },
        "top_cells": top,
        "ml_top_cells": [
            {
                "cell_id": str(r["cell_id"]),
                "aoi_id": str(r["aoi_id"]),
                "probability": round(float(r["probability"]), 3),
                "level": str(r["risk_class"]),
                "place": place,
            }
            for r, place in zip(ml_rows, ml_places, strict=True)
        ],
        "alerts_24h": int(alerts_24h or 0),
        "forecast_alerts_24h": int(forecast_24h or 0),
        "hazards": per_hazard,
        "cascades": cascades,
    }
    report["report_it"] = render_national_report_it(report)
    return report


async def _per_hazard_blocks(
    places: Callable[[list[str]], Awaitable[list[str | None]]],
) -> list[dict[str, Any]]:
    """One summary block per scorable hazard, for the report's hazard sections.

    ``places`` is threaded in rather than called here so the whole report
    resolves comune names in one batch: the lookup goes to GeoServer, and one
    call per hazard would triple that traffic for a page that already has the
    points in hand.
    """
    from limen.data.repos.hazards_repo import scorable_with_labels

    labelled = await scorable_with_labels()
    blocks: list[dict[str, Any]] = []
    for hazard, label in labelled:
        summary = await risk_summary(hazard=hazard.value)
        top = await top_risk_cells(limit=5, hazard=hazard.value)
        blocks.append(
            {
                "hazard": hazard.value,
                "label_it": label,
                "regions": summary,
                "totals": {
                    "regions": len(summary),
                    "cells": sum(r["cells_scored"] for r in summary),
                    "high_or_above": sum(r["high_or_above"] for r in summary),
                    "moderate": sum(r["moderate"] for r in summary),
                },
                "top_cells": top,
            }
        )

    flat = [c["cell_id"] for b in blocks for c in b["top_cells"]]
    names = await places(flat)
    it = iter(names)
    for b in blocks:
        for c in b["top_cells"]:
            c["place"] = next(it)
    return blocks


async def active_cascades() -> dict[str, Any]:
    """Cross-hazard rules currently firing, read from persisted scores (#58).

    Not recomputed: the post-fire multiplier is a field of the flood
    breakdown, so the report says what the engine actually applied rather than
    what it would apply now. A disabled rule reports nothing at all — the
    section must not imply a cascade is watching when ``cascades.yaml`` turned
    it off.
    """
    from limen.core.cascades import load_cascades

    rules = load_cascades()
    out: dict[str, Any] = {}

    if rules.post_fire_flood.enabled:
        async with acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT count(*) AS cells,
                       max((factors->>'post_fire_multiplier')::float) AS max_multiplier,
                       min((factors->>'months_since_fire')::float) AS min_months
                FROM risk_assessments
                WHERE hazard_type = 'flood'
                  -- Ultimo giorno: limita la scansione alle partizioni
                  -- correnti, e una cascata "attiva" è per definizione
                  -- quella dell'ultimo passaggio.
                  AND computed_at >= now() - interval '24 hours'
                  AND (factors->>'post_fire_multiplier')::float > 1.0
                """
            )
        out["post_fire_flood"] = {
            "window_months": rules.post_fire_flood.window_months,
            "cells": int(row["cells"] or 0) if row else 0,
            "max_multiplier": (
                round(float(row["max_multiplier"]), 3)
                if row and row["max_multiplier"] is not None
                else None
            ),
            "months_since_fire_min": (
                round(float(row["min_months"]), 1)
                if row and row["min_months"] is not None
                else None
            ),
        }

    if rules.joint_rain.enabled:
        # La soglia della regola, non quella della vista: `v_multi_hazard`
        # pubblica due livelli precotti (Moderate+ e High+) e `min_level` può
        # essere qualunque classe, quindi il conteggio si fa sui livelli
        # espansi dalla scala — esatto per ogni valore configurato.
        at_or_above = list(_LEVELS[_LEVELS.index(rules.joint_rain.min_level.value) :])
        async with acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cell_id, aoi_id,
                       max(risk_score) AS worst_score,
                       array_agg(hazard_type::text ORDER BY hazard_type::text) AS hazards
                FROM mv_latest_risk
                WHERE risk_level::text = ANY($1::text[])
                GROUP BY cell_id, aoi_id
                HAVING count(*) >= 2
                ORDER BY max(risk_score) DESC NULLS LAST, cell_id
                LIMIT 10
                """,
                at_or_above,
            )
            total = await conn.fetchval(
                """
                SELECT count(*) FROM (
                    SELECT cell_id FROM mv_latest_risk
                    WHERE risk_level::text = ANY($1::text[])
                    GROUP BY cell_id HAVING count(*) >= 2
                ) j
                """,
                at_or_above,
            )
        out["joint_rain"] = {
            "min_level": rules.joint_rain.min_level.value,
            "window_hours": rules.joint_rain.window_hours,
            "cells": int(total or 0),
            "top_cells": [
                {
                    "cell_id": str(r["cell_id"]),
                    "aoi_id": str(r["aoi_id"]),
                    "score": round(float(r["worst_score"]), 3),
                    "hazards": list(r["hazards"] or []),
                }
                for r in rows
            ],
        }

    return out


async def multi_hazard_summary(
    cell_id: str | None = None, aoi_id: str | None = None
) -> dict[str, Any]:
    """Quadro di una cella o di un'AOI su tutti i pericoli valutati (#58).

    The one tool that answers "what is threatening this place", as opposed to
    "how bad is this hazard here" — every other read tool takes a hazard and
    reports on that one alone, which makes the cross-hazard question N calls
    and a client-side join.
    """
    if not cell_id and not aoi_id:
        raise ValueError("serve cell_id oppure aoi_id")

    async with acquire() as conn:
        if cell_id:
            rows = await conn.fetch(
                """
                SELECT hazard_type, risk_score, risk_level, computed_at
                FROM mv_latest_risk
                WHERE cell_id = $1
                ORDER BY hazard_type
                """,
                cell_id,
            )
            worst = await conn.fetchrow(
                """
                SELECT aoi_id, worst_hazard, worst_level, worst_score,
                       hazards_at_moderate, hazards_at_high
                FROM v_multi_hazard WHERE cell_id = $1
                """,
                cell_id,
            )
            if worst is None:
                raise ValueError(f"cella sconosciuta: {cell_id!r}")
            return {
                "scope": "cell",
                "cell_id": cell_id,
                "aoi_id": str(worst["aoi_id"]),
                "worst_hazard": (
                    str(worst["worst_hazard"]) if worst["worst_level"] is not None else None
                ),
                "worst_level": (
                    str(worst["worst_level"]) if worst["worst_level"] is not None else None
                ),
                "hazards_at_moderate": list(worst["hazards_at_moderate"] or []),
                "hazards_at_high": list(worst["hazards_at_high"] or []),
                "per_hazard": [
                    {
                        "hazard": str(r["hazard_type"]),
                        "score": (
                            round(float(r["risk_score"]), 3)
                            if r["risk_score"] is not None
                            else None
                        ),
                        "level": str(r["risk_level"]) if r["risk_level"] is not None else None,
                        "computed_at": (r["computed_at"].isoformat() if r["computed_at"] else None),
                    }
                    for r in rows
                ],
            }

        agg = await conn.fetch(
            """
            SELECT hazard_type,
                   count(*) FILTER (WHERE risk_score IS NOT NULL) AS cells_scored,
                   max(risk_score) AS max_score,
                   count(*) FILTER (WHERE risk_level IN ('High','VeryHigh')) AS high_or_above,
                   count(*) FILTER (WHERE risk_level = 'Moderate') AS moderate,
                   max(computed_at) AS computed_at
            FROM mv_latest_risk
            WHERE aoi_id = $1
            GROUP BY hazard_type
            ORDER BY hazard_type
            """,
            aoi_id,
        )
        joint = await conn.fetchval(
            """SELECT count(*) FROM v_multi_hazard
               WHERE aoi_id = $1 AND array_length(hazards_at_high, 1) >= 2""",
            aoi_id,
        )
    if not agg:
        raise ValueError(f"AOI sconosciuta o senza valutazioni: {aoi_id!r}")
    return {
        "scope": "aoi",
        "aoi_id": aoi_id,
        "cells_multi_hazard_high": int(joint or 0),
        "per_hazard": [
            {
                "hazard": str(r["hazard_type"]),
                "cells_scored": int(r["cells_scored"] or 0),
                "max_score": (
                    round(float(r["max_score"]), 3) if r["max_score"] is not None else None
                ),
                "high_or_above": int(r["high_or_above"] or 0),
                "moderate": int(r["moderate"] or 0),
                "computed_at": r["computed_at"].isoformat() if r["computed_at"] else None,
            }
            for r in agg
        ],
    }


def _render_hazard_sections_it(report: dict[str, Any]) -> list[str]:
    """Una riga per pericolo. Solo numeri già nel report, come il resto."""
    blocks = report.get("hazards") or []
    # Con un solo pericolo valutato le sezioni ripeterebbero il paragrafo
    # principale parola per parola.
    if len(blocks) < 2:
        return []
    lines = ["", "Per tipo di pericolo:"]
    for b in blocks:
        t = b["totals"]
        label = str(b["label_it"]).lower()
        if t["cells"] == 0:
            lines.append(f"· {label}: nessuna valutazione disponibile.")
            continue
        pezzi = []
        if t["high_or_above"]:
            pezzi.append(f"{t['high_or_above']} zone a rischio alto")
        if t["moderate"]:
            pezzi.append(f"{t['moderate']} moderate")
        stato = ", ".join(pezzi) if pezzi else "nessuna zona sopra il livello basso"
        riga = f"· {label}: {stato}"
        top = b["top_cells"][0] if b["top_cells"] else None
        # Il punto peggiore si nomina solo se merita attenzione: a rischio
        # basso sarebbe il massimo di una lista tranquilla, e leggerlo
        # accanto a un nome di paese lo fa sembrare un avviso.
        if top and top["level"] in ("High", "VeryHigh"):
            dove = top.get("place") or "una zona non abitata"
            riga += f" — il punto peggiore è {dove} ({top['score']:.2f})"
        lines.append(riga + ".")
    return lines


def _render_cascade_section_it(report: dict[str, Any]) -> list[str]:
    """Sezione cascate: cosa un pericolo sta facendo a un altro, in italiano."""
    casc = report.get("cascades") or {}
    lines: list[str] = []

    pff = casc.get("post_fire_flood")
    if pff and pff["cells"]:
        lines.append(
            f"Effetto post-incendio: {pff['cells']} aree bruciate negli ultimi "
            f"{pff['window_months']:.0f} mesi hanno il terreno che assorbe meno, "
            f"quindi il rischio di allagamento è più alto del normale "
            f"(fino a {pff['max_multiplier']:.1f} volte)."
        )

    jr = casc.get("joint_rain")
    if jr and jr["cells"]:
        top = jr["top_cells"][0] if jr["top_cells"] else None
        riga = (
            f"Rischio combinato: {jr['cells']} aree sono sopra la soglia per "
            f"più di un pericolo contemporaneamente"
        )
        if top:
            quali = " e ".join(top["hazards"])
            riga += f" (la più critica: {quali})"
        lines.append(riga + ".")

    return ["", *lines] if lines else []


def render_national_report_it(report: dict[str, Any]) -> str:
    """Rendering italiano per non esperti — righe brevi, un fatto per riga.

    Deterministico: solo numeri presenti nel report. Il frontend lo
    mostra con ``white-space: pre-line``, i canali testuali (Telegram,
    webhook) beneficiano delle stesse interruzioni di riga.
    """
    t = report["totals"]
    dt = datetime.fromisoformat(report["generated_at"])
    lines = [f"Aggiornamento del {dt:%d/%m/%Y} alle {dt:%H:%M} UTC.", ""]

    if t["high_or_above"] > 0:
        hot = [r for r in report["regions"] if r["high_or_above"] > 0]
        dove = ", ".join(
            f"{r['aoi_id'].removeprefix('it-').replace('-', ' ').title()} ({r['high_or_above']})"
            for r in hot[:5]
        )
        lines.append(f"⚠ {t['high_or_above']} zone a rischio ALTO o molto alto: {dove}.")
    else:
        lines.append("Nessuna zona d'Italia è a rischio alto in questo momento.")

    def _it(n: int) -> str:
        return f"{n:,}".replace(",", ".")

    regioni = "1 regione" if t["regions"] == 1 else f"{t['regions']} regioni"
    lines.append(
        f"{_it(t['moderate'])} aree da 1 km² mostrano un rischio moderato, "
        f"su {_it(t['cells'])} monitorate in {regioni}."
    )

    if report["top_cells"]:
        c = report["top_cells"][0]
        dove = c.get("place") or "una zona non abitata"
        regione = c["aoi_id"].removeprefix("it-").replace("-", " ").title()
        lines.append(
            f"Il punto da tenere d'occhio è {dove}, in {regione} (punteggio {c['score']:.2f} su 1)."
        )

    if report["ml_top_cells"]:
        m = report["ml_top_cells"][0]
        dove = m.get("place") or "una zona non abitata"
        lines.append(
            f"Il modello sperimentale di intelligenza artificiale — in fase di "
            f"osservazione, non genera allerte — indica {dove} come probabilità "
            f"più alta ({m['probability']:.0%})."
        )

    lines.extend(_render_hazard_sections_it(report))
    lines.extend(_render_cascade_section_it(report))

    lines.append("")
    prev = report["forecast_alerts_24h"]
    prev_txt = (
        "nessuna criticità prevista a 48 ore"
        if prev == 0
        else f"{prev} allerte previsionali a 48 ore"
    )
    lines.append(f"Nelle ultime 24 ore: {report['alerts_24h']} allerte operative, {prev_txt}.")
    return "\n".join(lines)
