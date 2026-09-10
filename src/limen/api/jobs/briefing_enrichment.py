"""Briefing narrativo, dopo lo sweep e non dentro (#78).

Lo sweep orario gira con `profile="hourly"`: nessun nodo LLM, quindi
`explanation.briefing_it` esce NULL. Questo job passa ogni
``LLM__BRIEFING_INTERVAL_MINUTES``, guarda in `job_runs` quali regioni sono
state valutate senza narrativa nelle ultime ``LLM__BRIEFING_LOOKBACK_HOURS``,
e riscrive la narrativa sulle righe già persistite.

Perché spostarlo qui invece di renderlo più veloce: sulla Basilicata (10.353
celle) i due nodi LLM costavano 140,3 s dei 156 di sweep — RiskAnalyst 102,0 e
Briefing 38,3 — contro 0,88 s di scoring vero. Non erano lenti per un difetto
da correggere: generano prosa, e nessun consumatore la aspetta. La mappa mostra
il testo deterministico finché la narrativa non arriva, le allerte sono
deterministiche per invariante, e i punteggi non la vedono affatto.

**Una regione alla volta, nessun parallelismo.** È l'unico posto del sistema
dove la lentezza è ammessa, e ammetterla significa non moltiplicarla: venti
briefing concorrenti su un gateway locale sono venti timeout.
"""

from __future__ import annotations

import asyncio
from typing import Any

from limen.agents.chat_agents.briefing import BriefingAgent
from limen.agents.chat_agents.prompts_registry import has_narrative
from limen.agents.chat_agents.risk_analyst import RiskAnalystAgent
from limen.agents.workflows.main_workflow import level_reached
from limen.api.dependencies import AppDependencies
from limen.api.jobs._tracking import tracked
from limen.api.jobs.ids import (
    JOB_BRIEFING_ENRICHMENT,
    JOB_FIRMS_MONITORING,
    JOB_HOURLY_MONITORING,
    JOB_NOWCAST_MONITORING,
)
from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.repos import assessment_repo, job_runs_repo

log = get_logger(__name__)

# Un modello locale può metterci minuti per briefing: con l'intervallo a 10 e
# venti regioni escalate, i tick si sovrappongono. Quello che trova il lock
# occupato salta — la lista dei candidati è ricostruita da zero ogni volta,
# quindi nulla si perde.
_lock = asyncio.Lock()

#: I job che scrivono `risk_assessments` con il profilo `hourly`, cioè senza
#: narrativa. Non solo lo sweep orario: nowcast radar e FIRMS sono trigger
#: event-driven con tick di 15 e 45 minuti, e dopo la #78 girano anche loro
#: senza LLM — se non fossero elencati qui, una regione valutata perché il
#: radar ha visto un nubifragio resterebbe senza analisi proprio nell'ora in
#: cui serve.
SOURCE_JOBS = (JOB_HOURLY_MONITORING, JOB_NOWCAST_MONITORING, JOB_FIRMS_MONITORING)


def _candidates(
    runs: list[job_runs_repo.JobRun], *, min_level: str
) -> list[tuple[str, HazardType, int]]:
    """``(aoi_id, hazard, run_id)`` degli sweep che meritano una narrativa.

    Il più recente per (regione, pericolo) e basta: una regione valutata due
    volte nella finestra ha una sola riga che qualcuno legge — `mv_latest_risk`
    tiene l'ultima — e raccontare anche quella di due ore fa sarebbe spendere
    un briefing per una pagina che nessuno apre.
    """
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, HazardType, int]] = []
    for run in runs:  # già ordinati dal più recente
        if run.status != "ok" or run.scope is None:
            continue
        metrics = run.metrics
        if metrics.get("llm_called"):
            continue
        run_id = metrics.get("assessment_id")
        if not isinstance(run_id, int):
            # Sweep anteriore a #76, o fallito prima di persistere: non c'è
            # nessuna riga da arricchire.
            continue
        hazard = HazardType(str(metrics.get("hazard", DEFAULT_HAZARD.value)))
        key = (run.scope, hazard.value)
        if key in seen:
            continue
        seen.add(key)
        if not has_narrative(hazard):
            continue
        if not level_reached(dict(metrics.get("cells_by_level") or {}), min_level):
            continue
        out.append((run.scope, hazard, run_id))
    return out


async def _enrich_one(
    *,
    analyst: RiskAnalystAgent,
    briefer: BriefingAgent,
    aoi_id: str,
    hazard: HazardType,
    run_id: int,
) -> int:
    """Genera analisi + briefing per uno sweep e li riattacca. Ritorna le righe toccate."""
    assessment = await assessment_repo.summary_by_run(run_id)
    if assessment is None:
        log.info("job.briefing_enrichment.skip", reason="no rows", run_id=run_id, aoi_id=aoi_id)
        return 0
    if assessment.briefing_it:
        # Già arricchito da un tick precedente: la metrica in `job_runs` dice
        # com'era finito lo sweep, non com'è la riga adesso.
        log.info("job.briefing_enrichment.skip", reason="already", run_id=run_id, aoi_id=aoi_id)
        return 0

    analysis = await analyst.analyse(assessment)
    payload: dict[str, Any] = analysis.model_dump()
    briefing = await briefer.brief(assessment, analysis=analysis)
    rows = await assessment_repo.attach_narrative(run_id, briefing_it=briefing, analysis=payload)
    log.info(
        "job.briefing_enrichment.done",
        aoi_id=aoi_id,
        hazard=hazard.value,
        run_id=run_id,
        rows=rows,
        chars=len(briefing),
    )
    return rows


async def run_briefing_enrichment(deps: AppDependencies) -> dict[str, int]:
    """Arricchisci gli sweep recenti rimasti senza narrativa. Ritorna ``{aoi: righe}``."""
    if _lock.locked():
        log.info("job.briefing_enrichment.skip", reason="previous run still going")
        return {}
    async with _lock:
        return await _run(deps)


async def _run(deps: AppDependencies) -> dict[str, int]:
    llm = deps.settings.llm
    runs: list[job_runs_repo.JobRun] = []
    for job_id in SOURCE_JOBS:
        runs.extend(await job_runs_repo.finished_since(job_id, hours=llm.briefing_lookback_hours))
    # Un solo ordinamento su tutte le sorgenti: `_candidates` tiene il primo
    # per regione, e mescolare tre liste già ordinate non dà una lista ordinata.
    runs.sort(key=lambda r: r.finished_at or r.started_at, reverse=True)
    pending = _candidates(runs, min_level=llm.briefing_min_level)
    if not pending:
        log.info("job.briefing_enrichment.nothing", considered=len(runs))
        return {}

    analyst = RiskAnalystAgent(deps.llm_factory.create("RiskAnalyst"))
    briefer = BriefingAgent(deps.llm_factory.create("Briefing"), grounding=deps.grounding_service)
    out: dict[str, int] = {}
    for aoi_id, hazard, run_id in pending:
        # Una riga per regione, come lo sweep: dice quale briefing è lento.
        async with tracked(JOB_BRIEFING_ENRICHMENT, scope=aoi_id) as metrics:
            metrics["hazard"] = hazard.value
            metrics["run_id"] = run_id
            try:
                rows = await _enrich_one(
                    analyst=analyst,
                    briefer=briefer,
                    aoi_id=aoi_id,
                    hazard=hazard,
                    run_id=run_id,
                )
            except Exception as exc:
                # Una regione che esplode non deve lasciare le altre senza
                # narrativa: il ciclo prosegue, la riga resta `error`.
                log.error(
                    "job.briefing_enrichment.error",
                    aoi_id=aoi_id,
                    run_id=run_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                metrics["status"] = "error"
                metrics["error_type"] = type(exc).__name__
                continue
            metrics["rows"] = rows
            if rows == 0:
                metrics["status"] = "skipped"
            out[aoi_id] = out.get(aoi_id, 0) + rows
    log.info("job.briefing_enrichment.summary", aois=len(out), per_aoi=out)
    return out
