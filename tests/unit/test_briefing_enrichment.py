"""Selezione dei candidati per il briefing asincrono (#78).

La generazione vera è una chiamata LLM e un UPDATE: sono coperti altrove
(`tests/integration/test_briefing_enrichment_db.py` per l'invarianza numerica).
Qui sta la regola che decide *quali* sweep raccontare, che è dove si sbaglia:
raccontarne uno di troppo costa minuti di gateway, dimenticarne uno lascia una
regione escalata con il solo testo deterministico.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from limen.api.jobs.briefing_enrichment import _candidates
from limen.core.models.hazard import HazardType
from limen.data.repos.job_runs_repo import JobRun


def _run(scope: str, *, status: str = "ok", **metrics: Any) -> JobRun:
    base: dict[str, Any] = {
        "llm_called": False,
        "assessment_id": 1,
        "hazard": "landslide",
        "cells_by_level": {"High": 3},
    }
    base.update(metrics)
    now = datetime.now(UTC)
    return JobRun(
        id=1,
        job_id="limen-hourly-monitoring",
        scope=scope,
        started_at=now,
        finished_at=now,
        status=status,
        metrics=base,
        error=None,
        host="test",
    )


def test_an_escalated_sweep_without_narrative_is_a_candidate() -> None:
    assert _candidates([_run("it-basilicata")], min_level="Moderate") == [
        ("it-basilicata", HazardType.LANDSLIDE, 1)
    ]


def test_a_sweep_that_already_called_the_llm_is_not() -> None:
    """`monitor-once` e il profilo previsionale la narrativa ce l'hanno già:
    rigenerarla sarebbe spendere un briefing per sovrascriverne uno uguale."""
    assert _candidates([_run("it-puglia", llm_called=True)], min_level="Moderate") == []


def test_a_quiet_sweep_is_not() -> None:
    """Sotto `briefing_min_level` il nodo LLM saltava dentro lo sweep; il job
    asincrono deve saltare per la stessa ragione, non generare venti briefing
    di notte per dire che non succede niente."""
    assert _candidates([_run("it-molise", cells_by_level={"Low": 900})], min_level="Moderate") == []


def test_a_failed_sweep_is_not() -> None:
    assert _candidates([_run("it-lazio", status="error")], min_level="Moderate") == []


def test_a_sweep_that_never_persisted_is_not() -> None:
    """Senza `assessment_id` non c'è nessun `run_id` da aggiornare: sono le
    righe scritte prima di #76, o uno sweep esploso prima di persistere."""
    assert _candidates([_run("it-marche", assessment_id=None)], min_level="Moderate") == []


def test_a_hazard_without_a_prompt_is_not() -> None:
    """Nessuna prosa è meglio di prosa sbagliata: il prompt del briefing si
    apre con "spiega il rischio frane"."""
    assert _candidates([_run("it-sicilia", hazard="wildfire")], min_level="Moderate") == []


def test_only_the_most_recent_sweep_per_region_wins() -> None:
    """Una regione valutata due volte nella finestra ha una sola riga che
    qualcuno legge — `mv_latest_risk` tiene l'ultima."""
    # `finished_since` li restituisce dal più recente, ed è l'ordine su cui
    # `_candidates` si appoggia per tenere il primo.
    runs = [_run("it-puglia", assessment_id=9), _run("it-puglia", assessment_id=8)]
    assert _candidates(runs, min_level="Moderate") == [("it-puglia", HazardType.LANDSLIDE, 9)]


def test_min_level_none_takes_every_sweep() -> None:
    quiet = _run("it-umbria", cells_by_level={"Low": 12})
    assert _candidates([quiet], min_level="None") == [("it-umbria", HazardType.LANDSLIDE, 1)]
