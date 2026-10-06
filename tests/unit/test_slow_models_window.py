"""Colibrì solo di notte (#155).

Il server è uno: di giorno serve la mappa e gli sweep, e un modello che legge
400 GB da disco e genera a 0,08 token/s gli toglierebbe le risorse. La
finestra è in ore UTC e può stare a cavallo della mezzanotte.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from limen.api.jobs import briefing_enrichment
from limen.config.settings import LLMSettings


def test_la_finestra_di_default_e_notturna_e_chiude_prima_delle_due() -> None:
    llm = LLMSettings()
    assert llm.slow_models_window_utc == (20, 2)
    assert llm.slow_models_allowed(21)
    assert llm.slow_models_allowed(0)
    assert not llm.slow_models_allowed(2)
    assert not llm.slow_models_allowed(12)


def test_una_finestra_dentro_la_stessa_giornata() -> None:
    llm = LLMSettings(slow_models_window_utc=(1, 5))
    assert llm.slow_models_allowed(1)
    assert not llm.slow_models_allowed(5)


@pytest.mark.parametrize(("ora", "chiamato"), [(12, False), (22, True)])
async def test_il_briefing_con_colibri_aspetta_la_notte(
    monkeypatch: pytest.MonkeyPatch, ora: int, chiamato: bool
) -> None:
    llm = LLMSettings(models={"briefing": "quality-local"})
    deps: Any = SimpleNamespace(settings=SimpleNamespace(llm=llm))
    cercati = AsyncMock(return_value=[])
    monkeypatch.setattr(briefing_enrichment.job_runs_repo, "finished_since", cercati)

    class _Ora(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 10, 6, ora, 0, tzinfo=UTC)

    monkeypatch.setattr(briefing_enrichment, "datetime", _Ora)
    assert await briefing_enrichment._run(deps) == {}
    assert cercati.called is chiamato


async def test_un_modello_veloce_non_aspetta(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = LLMSettings(models={"briefing": "chat"})
    deps: Any = SimpleNamespace(settings=SimpleNamespace(llm=llm))
    cercati = AsyncMock(return_value=[])
    monkeypatch.setattr(briefing_enrichment.job_runs_repo, "finished_since", cercati)
    await briefing_enrichment._run(deps)
    assert cercati.called
