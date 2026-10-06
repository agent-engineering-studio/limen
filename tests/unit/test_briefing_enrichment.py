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

import pytest

from limen.api.jobs import briefing_enrichment as be
from limen.api.jobs.briefing_enrichment import _candidates
from limen.config.settings import LLMSettings
from limen.core.models.hazard import HazardType
from limen.data.repos import spiegazioni_repo
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


def test_a_hazard_without_a_prompt_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nessuna prosa è meglio di prosa sbagliata: un pericolo senza il suo
    prompt non riceve quello di un altro."""
    monkeypatch.setattr(be, "has_narrative", lambda h: h is HazardType.LANDSLIDE)
    assert _candidates([_run("it-sicilia", hazard="wildfire")], min_level="Moderate") == []


def test_l_incendio_ha_ora_la_sua_spiegazione() -> None:
    """#155: alluvione e incendio hanno i loro prompt."""
    assert _candidates([_run("it-sicilia", hazard="wildfire")], min_level="Moderate") == [
        ("it-sicilia", HazardType.WILDFIRE, 1)
    ]


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


# ---------------------------------------------------------------------------
# Arricchimento vero e proprio: agenti e repository finti (#116)
# ---------------------------------------------------------------------------


class _Analysis:
    def model_dump(self) -> dict[str, Any]:
        return {"driver": "rain", "anomalies": [], "attention_window_hours": 24, "confidence": 0.7}


class _Analyst:
    async def analyse(self, _assessment: Any) -> _Analysis:
        return _Analysis()


class _Briefer:
    def __init__(self, testo: str = "Testo del briefing.") -> None:
        self.testo = testo

    async def brief(self, _assessment: Any, *, analysis: Any) -> str:
        return self.testo


def _esistente(run_id: int, *, ripiego: bool) -> spiegazioni_repo.Spiegazione:
    return spiegazioni_repo.Spiegazione(
        aoi_id="it-x",
        hazard=HazardType.LANDSLIDE,
        run_id=run_id,
        livello="High",
        scritta=datetime(2026, 10, 6, tzinfo=UTC),
        modello="quality-cloud",
        ripiego=ripiego,
        testo="già scritto",
        analisi=None,
    )


def _patch_repos(
    monkeypatch: Any, *, esistente: spiegazioni_repo.Spiegazione | None = None
) -> dict[str, Any]:
    scritto: dict[str, Any] = {}

    async def _summary(aoi_id: str, hazard: HazardType) -> object:
        return object()

    async def _leggi(aoi_id: str, hazard: HazardType) -> Any:
        return esistente

    async def _scrivi(**kw: Any) -> None:
        scritto.update(kw)

    monkeypatch.setattr(be.assessment_repo, "summary_for_region", _summary)
    monkeypatch.setattr(be.spiegazioni_repo, "leggi", _leggi)
    monkeypatch.setattr(be.spiegazioni_repo, "scrivi", _scrivi)
    monkeypatch.setattr(be, "briefing_di_ripiego", lambda _a: "Testo deterministico.")
    return scritto


async def _enrich(briefer: Any, *, analyst: Any = None, run_id: int = 7) -> int:
    return await be._enrich_one(
        analyst=analyst or _Analyst(),
        briefer=briefer,
        aoi_id="it-basilicata",
        hazard=HazardType.LANDSLIDE,
        run_id=run_id,
        livello="High",
        modello="quality-cloud",
    )


async def test_la_spiegazione_va_nella_tabella_della_regione(monkeypatch: Any) -> None:
    scritto = _patch_repos(monkeypatch)
    assert await _enrich(_Briefer()) == 1
    assert scritto["aoi_id"] == "it-basilicata"
    assert scritto["run_id"] == 7
    assert scritto["testo"] == "Testo del briefing."
    assert scritto["modello"] == "quality-cloud"
    assert scritto["ripiego"] is False
    assert scritto["analisi"]["driver"] == "rain"


async def test_un_ripiego_si_salva_ma_non_conta_come_spiegata(monkeypatch: Any) -> None:
    """Il modello non ha risposto: il testo è quello deterministico. Si salva
    marcato, così la SPA non lo attribuisce all'AI, e al tick dopo si riprova."""
    scritto = _patch_repos(monkeypatch)
    assert await _enrich(_Briefer("Testo deterministico.")) == 0
    assert scritto["ripiego"] is True


async def test_una_regione_senza_stato_o_gia_spiegata_non_chiama_l_llm(monkeypatch: Any) -> None:
    class _NeverCalled:
        async def analyse(self, _a: Any) -> Any:
            raise AssertionError("l'LLM non doveva essere chiamato")

    _patch_repos(monkeypatch, esistente=_esistente(1, ripiego=False))
    assert await _enrich(_Briefer(), analyst=_NeverCalled(), run_id=1) == 0

    async def _nessuno(aoi_id: str, hazard: HazardType) -> None:
        return None

    monkeypatch.setattr(be.assessment_repo, "summary_for_region", _nessuno)
    assert await _enrich(_Briefer(), analyst=_NeverCalled()) == 0


async def test_dopo_un_ripiego_lo_stesso_sweep_si_riprova(monkeypatch: Any) -> None:
    _patch_repos(monkeypatch, esistente=_esistente(7, ripiego=True))
    assert await _enrich(_Briefer(), run_id=7) == 1


class _Settings:
    class llm:  # noqa: N801
        briefing_lookback_hours = 3
        briefing_min_level = "Moderate"
        briefing_min_hours = 12
        models = LLMSettings().models
        slow_models_allowed = LLMSettings().slow_models_allowed


class _Factory:
    def create(self, _role: str) -> object:
        return object()


class _Deps:
    settings = _Settings()
    llm_factory = _Factory()
    grounding_service = None


def _patch_tracking(monkeypatch: Any) -> list[dict[str, Any]]:
    """`tracked` scrive in `job_runs`: qui si registra cosa avrebbe scritto."""
    from contextlib import asynccontextmanager

    rows: list[dict[str, Any]] = []

    @asynccontextmanager
    async def _tracked(_job: str, *, scope: str | None = None):
        metrics: dict[str, Any] = {"scope": scope}
        yield metrics
        rows.append(metrics)

    monkeypatch.setattr(be, "tracked", _tracked)

    async def _nessuna(_hours: int) -> dict[tuple[str, str], str]:
        return {}

    monkeypatch.setattr(be.spiegazioni_repo, "recenti", _nessuna)
    monkeypatch.setattr(be, "RiskAnalystAgent", lambda _c: _Analyst())
    monkeypatch.setattr(be, "BriefingAgent", lambda _c, grounding=None: _Briefer())
    return rows


async def test_run_with_nothing_to_do_calls_no_agent(monkeypatch: Any) -> None:
    async def _finished(_job: str, *, hours: int) -> list[Any]:
        return []

    monkeypatch.setattr(be.job_runs_repo, "finished_since", _finished)
    tracked_rows = _patch_tracking(monkeypatch)
    assert await be.run_briefing_enrichment(_Deps()) == {}
    assert tracked_rows == []


async def test_run_enriches_each_candidate_and_isolates_failures(monkeypatch: Any) -> None:
    """Una regione che esplode non lascia le altre senza narrativa, e la sua
    riga di tracciatura resta `error`."""
    runs = {
        "limen-hourly-monitoring": [_run("it-puglia", assessment_id=1)],
        "limen-nowcast-monitoring": [_run("it-molise", assessment_id=2)],
    }

    async def _finished(job: str, *, hours: int) -> list[Any]:
        return runs.get(job, [])

    async def _enrich(**kw: Any) -> int:
        if kw["aoi_id"] == "it-molise":
            raise RuntimeError("gateway giù")
        return 5

    monkeypatch.setattr(be.job_runs_repo, "finished_since", _finished)
    monkeypatch.setattr(be, "_enrich_one", _enrich)
    tracked_rows = _patch_tracking(monkeypatch)

    out = await be.run_briefing_enrichment(_Deps())

    assert out == {"it-puglia": 5}
    by_scope = {r["scope"]: r for r in tracked_rows}
    assert by_scope["it-molise"]["status"] == "error"
    assert by_scope["it-puglia"]["rows"] == 5


async def test_run_marks_a_zero_row_enrichment_as_skipped(monkeypatch: Any) -> None:
    async def _finished(job: str, *, hours: int) -> list[Any]:
        return [_run("it-puglia", assessment_id=1)] if job == "limen-hourly-monitoring" else []

    async def _enrich(**_kw: Any) -> int:
        return 0

    monkeypatch.setattr(be.job_runs_repo, "finished_since", _finished)
    monkeypatch.setattr(be, "_enrich_one", _enrich)
    tracked_rows = _patch_tracking(monkeypatch)
    await be.run_briefing_enrichment(_Deps())
    assert tracked_rows[0]["status"] == "skipped"


async def test_a_concurrent_tick_is_skipped(monkeypatch: Any) -> None:
    """Un modello locale può metterci minuti: il tick che trova il lock occupato
    salta, e la lista dei candidati si ricostruisce comunque al giro dopo."""
    await be._lock.acquire()
    try:
        assert await be.run_briefing_enrichment(_Deps()) == {}
    finally:
        be._lock.release()


def test_la_classe_dominante_e_la_piu_alta_con_celle() -> None:
    assert be.livello_dominante({"Low": 5, "High": 1, "VeryHigh": 0}) == "High"
    assert be.livello_dominante({}) == "None"


async def test_una_regione_gia_spiegata_con_la_stessa_classe_non_si_rispiega(
    monkeypatch: Any,
) -> None:
    """Ogni sweep orario è un run nuovo: senza questo filtro una regione
    ferma si rispiegherebbe ogni ora. La fonte è la tabella delle
    spiegazioni, non `job_runs`."""

    async def _finished(job: str, *, hours: int) -> list[Any]:
        if job != "limen-hourly-monitoring":
            return []
        return [
            _run("it-puglia", assessment_id=1, cells_by_level={"High": 3}),
            _run("it-molise", assessment_id=2, cells_by_level={"High": 3}),
        ]

    async def _recenti(_hours: int) -> dict[tuple[str, str], str]:
        return {("it-puglia", "landslide"): "High", ("it-molise", "landslide"): "Moderate"}

    viste: list[str] = []

    async def _enrich(**kw: Any) -> int:
        viste.append(kw["aoi_id"])
        return 1

    monkeypatch.setattr(be.job_runs_repo, "finished_since", _finished)
    _patch_tracking(monkeypatch)
    monkeypatch.setattr(be.spiegazioni_repo, "recenti", _recenti)
    monkeypatch.setattr(be, "_enrich_one", _enrich)
    await be.run_briefing_enrichment(_Deps())
    # Puglia è già spiegata alla stessa classe; il Molise è salito.
    assert viste == ["it-molise"]
