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
from datetime import UTC, datetime
from typing import Any

from limen.agents.chat_agents.briefing import BriefingAgent, briefing_di_ripiego
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
from limen.config.settings import SLOW_GENERATION_MODELS
from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.repos import assessment_repo, job_runs_repo, spiegazioni_repo

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


_ORDINE_LIVELLI = ("None", "Low", "Moderate", "High", "VeryHigh")


def livello_dominante(cells_by_level: dict[str, Any]) -> str:
    """La classe più alta con almeno una cella: è ciò che la spiegazione racconta."""
    presenti = [lv for lv in _ORDINE_LIVELLI if int(cells_by_level.get(lv) or 0) > 0]
    return presenti[-1] if presenti else "None"


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
    livello: str,
    modello: str,
) -> int:
    """Scrive analisi + spiegazione di una regione. Ritorna 1 se l'ha scritta l'AI."""
    assessment = await assessment_repo.summary_for_region(aoi_id, hazard)
    if assessment is None:
        log.info("job.briefing_enrichment.skip", reason="no state", run_id=run_id, aoi_id=aoi_id)
        return 0
    esistente = await spiegazioni_repo.leggi(aoi_id, hazard)
    if esistente is not None and esistente.run_id == run_id and not esistente.ripiego:
        # Già raccontato da un tick precedente: la metrica in `job_runs` dice
        # com'era finito lo sweep, non se la spiegazione c'è.
        log.info("job.briefing_enrichment.skip", reason="already", run_id=run_id, aoi_id=aoi_id)
        return 0

    analysis = await analyst.analyse(assessment)
    briefing = await briefer.brief(assessment, analysis=analysis)
    ripiego = briefing == briefing_di_ripiego(assessment)
    await spiegazioni_repo.scrivi(
        aoi_id=aoi_id,
        hazard=hazard,
        run_id=run_id,
        livello=livello,
        modello=modello,
        ripiego=ripiego,
        testo=briefing,
        analisi=analysis.model_dump(),
    )
    log.info(
        "job.briefing_enrichment.done",
        aoi_id=aoi_id,
        hazard=hazard.value,
        run_id=run_id,
        ripiego=ripiego,
        chars=len(briefing),
    )
    # Un ripiego non conta come spiegata: al tick dopo si riprova, invece di
    # lasciare la regione col testo deterministico per `briefing_min_hours`.
    return 0 if ripiego else 1


async def run_briefing_enrichment(deps: AppDependencies) -> dict[str, int]:
    """Arricchisci gli sweep recenti rimasti senza narrativa. Ritorna ``{aoi: righe}``."""
    if _lock.locked():
        log.info("job.briefing_enrichment.skip", reason="previous run still going")
        return {}
    async with _lock:
        return await _run(deps)


async def _run(deps: AppDependencies) -> dict[str, int]:
    llm = deps.settings.llm
    modello = (llm.models.model_dump().get("briefing") or "").strip()
    ora = datetime.now(UTC).hour
    if modello in SLOW_GENERATION_MODELS and not llm.slow_models_allowed(ora):
        # Colibrì solo di notte: di giorno il server serve la mappa e gli
        # sweep. Le regioni restano in lista e si raccontano alla prima ora
        # utile, perché i candidati si ricostruiscono a ogni tick.
        log.info(
            "job.briefing_enrichment.skip",
            reason="slow model outside window",
            model=modello,
            hour_utc=ora,
        )
        return {}
    runs: list[job_runs_repo.JobRun] = []
    for job_id in SOURCE_JOBS:
        runs.extend(await job_runs_repo.finished_since(job_id, hours=llm.briefing_lookback_hours))
    # Un solo ordinamento su tutte le sorgenti: `_candidates` tiene il primo
    # per regione, e mescolare tre liste già ordinate non dà una lista ordinata.
    runs.sort(key=lambda r: r.finished_at or r.started_at, reverse=True)
    pending = _candidates(runs, min_level=llm.briefing_min_level)
    # Livello dominante di ciascun candidato, dalle metriche del suo sweep.
    livelli = {
        int(r.metrics["assessment_id"]): livello_dominante(
            dict(r.metrics.get("cells_by_level") or {})
        )
        for r in runs
        if isinstance(r.metrics.get("assessment_id"), int)
    }
    # Dalla tabella delle spiegazioni, non dalle righe di `job_runs`: quelle
    # dicevano «spiegata» anche quando lo sweep aveva già cancellato il testo
    # (prima della 064), e la regione restava muta fino a 12 ore.
    spiegate = await spiegazioni_repo.recenti(llm.briefing_min_hours)
    pending = [
        (aoi, hazard, run_id)
        for aoi, hazard, run_id in pending
        if spiegate.get((aoi, hazard.value)) != livelli.get(run_id)
    ]
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
            metrics["livello"] = livelli.get(run_id, "None")
            try:
                rows = await _enrich_one(
                    analyst=analyst,
                    briefer=briefer,
                    aoi_id=aoi_id,
                    hazard=hazard,
                    run_id=run_id,
                    livello=livelli.get(run_id, "None"),
                    modello=modello or "predefinito",
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
