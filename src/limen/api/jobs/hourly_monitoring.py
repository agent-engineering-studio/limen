"""Hourly job — run the MAF workflow for every active AOI."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from limen.api.dependencies import AppDependencies
from limen.api.jobs._tracking import tracked
from limen.api.jobs.ids import JOB_HOURLY_MONITORING
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire

log = get_logger(__name__)

# Lo sweep nazionale può durare più del tick orario: un secondo run
# concorrente raddoppia il carico sul DB e affama le regioni in coda.
# Il tick che trova il lock occupato salta (il prossimo riparte comunque
# stale-first, quindi nessuna regione resta indietro).
_sweep_lock = asyncio.Lock()


async def _aois_stale_first(hazard: HazardType = DEFAULT_HAZARD) -> list[str]:
    """AOIs ordered by oldest assessment first (never-assessed in testa).

    Lo sweep nazionale dura più del tick orario: con l'ordine alfabetico
    fisso le regioni in coda (Toscana, Veneto, …) non venivano MAI
    valutate — ogni tick ripartiva dalla testa.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id
            FROM aoi a
            LEFT JOIN (
                SELECT aoi_id, MAX(computed_at) AS ts
                FROM mv_latest_risk
                WHERE hazard_type = $1
                GROUP BY aoi_id
            ) m ON m.aoi_id = a.id
            ORDER BY m.ts ASC NULLS FIRST, a.id
            """,
            hazard.value,
        )
    return [str(r["id"]) for r in rows]


async def _hazards_stale_first(enabled: Sequence[HazardType]) -> list[HazardType]:
    """Hazards ordered by oldest assessment first.

    The AOI loop is stale-first for a reason: the national sweep outlives the
    tick, so a fixed order starves whatever comes last. With the hazard loop
    outermost, a fixed hazard order brings the same starvation back one level
    up — every restart would resume from the first hazard. Ordering both axes
    by staleness closes it.
    """
    if len(enabled) < 2:
        return list(enabled)
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT hazard_type, MAX(computed_at) AS ts
            FROM mv_latest_risk
            WHERE hazard_type = ANY($1::hazard_type[])
            GROUP BY hazard_type
            """,
            [h.value for h in enabled],
        )
    seen = {HazardType(r["hazard_type"]): r["ts"] for r in rows}
    # Never assessed sorts first; ties keep the configured order.
    return sorted(enabled, key=lambda h: (seen.get(h) is not None, seen.get(h)))


def _sweep_metrics(result: Any, *, cells: int) -> dict[str, Any]:
    """Metriche di un AOI, dai record che il workflow già produce.

    Il runtime misura ogni nodo in `NodeExecutionRecord.duration_seconds`
    (`workflow_runtime/builder.py`), quindi i tempi per passo sono già lì: la
    issue proponeva un dizionario `timings` sul contesto, ma sarebbe stato un
    secondo posto dove misurare la stessa cosa, e i due sarebbero divergiti al
    primo nodo aggiunto.

    I nomi dei nodi diventano chiavi `<nodo>_s` in minuscolo: `RiskScoring`
    → `riskscoring_s`. Leggibile e stabile — un nodo rinominato cambia la
    chiave, che è corretto: è un passo diverso.
    """
    ctx = result.context
    assessment = ctx.assessment
    out: dict[str, Any] = {
        "cells": cells,
        "assessment_id": ctx.assessment_id,
        # I due campi vivono su `AggregateAssessment`, non sul contesto, e si
        # chiamano `analysis` e `briefing_it`. Al primo giro li leggevo dal
        # contesto e la metrica diceva `llm_called=False` mentre 140 s su 156
        # erano andati all'LLM: una metrica che mente è peggio di nessuna.
        "llm_called": bool(
            assessment is not None and (assessment.analysis is not None or assessment.briefing_it)
        ),
    }
    if assessment is not None:
        out["high_or_above"] = assessment.cells_high_or_above
    for node in result.nodes:
        out[f"{node.name.lower()}_s"] = round(node.duration_seconds, 3)
    return out


async def run_hourly_monitoring(deps: AppDependencies) -> dict[str, int]:
    """Run the workflow over every AOI; return per-AOI cell counts."""
    if _sweep_lock.locked():
        log.info("job.hourly_monitoring.skip", reason="previous sweep still running")
        # Il salto si registra, e non come errore: è voluto. Non registrarlo
        # nasconderebbe che il sistema è in ritardo su se stesso, che è
        # esattamente il sintomo per cui questa tabella esiste (#75).
        async with tracked(JOB_HOURLY_MONITORING) as metrics:
            metrics["status"] = "skipped"
            metrics["reason"] = "previous sweep still running"
        return {}
    async with _sweep_lock:
        return await _run_sweep(deps)


async def _run_sweep(deps: AppDependencies) -> dict[str, int]:
    """Sweep every enabled hazard over every AOI.

    Keyed by AOI with the cell count summed across hazards, so with a single
    hazard enabled the numbers are exactly what this job has always returned.
    The per-hazard detail is in the log line, and lands in ``job_runs`` when
    #75 ships.
    """
    out: dict[str, int] = {}
    hazards = await _hazards_stale_first(deps.settings.hazards.enabled)
    if not hazards:
        log.warning("job.hourly_monitoring.no_hazards")
        return out

    for hazard in hazards:
        # Stale-first *per hazard*: each one has its own last-assessed time,
        # so ordering by a mixed timestamp would starve whichever hazard
        # happens to lag.
        aois = await _aois_stale_first(hazard)
        if not aois:
            log.info("job.hourly_monitoring.no_aois", hazard=hazard.value)
            continue
        try:
            workflow = deps.build_workflow(hazard=hazard)
        except Exception as exc:
            # A hazard that cannot be scored (no engine, no thresholds) must
            # not take the other hazards down with it.
            log.error(
                "job.hourly_monitoring.workflow_unavailable",
                hazard=hazard.value,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue
        for aoi_id in aois:
            ctx = MonitoringContext(
                aoi_id=aoi_id,
                hazard_type=hazard,
                valuation_time=datetime.now(UTC),
                enable_insitu=deps.settings.enable_insitu,
            )
            # Una riga per regione: una sola riga per sweep direbbe che è
            # durato N, venti dicono quale regione lo fa durare — che è
            # l'informazione che serve prima di ottimizzare (#74).
            async with tracked(JOB_HOURLY_MONITORING, scope=aoi_id) as metrics:
                metrics["hazard"] = hazard.value
                try:
                    result = await workflow.run(ctx)
                except Exception as exc:  # never bring the scheduler down
                    log.error(
                        "job.hourly_monitoring.error",
                        aoi_id=aoi_id,
                        hazard=hazard.value,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    metrics["status"] = "error"
                    metrics["error_type"] = type(exc).__name__
                    continue
                cells = len(result.context.cell_results)
                out[aoi_id] = out.get(aoi_id, 0) + cells
                metrics.update(_sweep_metrics(result, cells=cells))
                log.info(
                    "job.hourly_monitoring.aoi.done",
                    aoi_id=aoi_id,
                    hazard=hazard.value,
                    cells=cells,
                    assessment_id=result.context.assessment_id,
                )
    log.info(
        "job.hourly_monitoring.done",
        hazards=[h.value for h in hazards],
        aois=len(out),
        per_aoi=out,
    )
    return out
