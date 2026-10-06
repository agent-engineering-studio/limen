"""La spiegazione per ciascun pericolo (#155).

Fino ad allora solo le frane avevano un prompt, e gli agenti caricavano
quello anche per gli altri pericoli. Questi test fissano che ogni pericolo
riceve il suo prompt, i suoi dati grezzi e il suo testo di ripiego, e che i
numeri restano quelli del motore.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast

from limen.agents.chat_agents.briefing import (
    BriefingAgent,
    _note_pericolo,
    deterministic_briefing,
)
from limen.agents.chat_agents.briefing import (
    _load_system_prompt as prompt_briefing,
)
from limen.agents.chat_agents.risk_analyst import (
    RiskAnalysis,
    RiskAnalystAgent,
    _neutral_fallback,
)
from limen.agents.chat_agents.risk_analyst import (
    _load_system_prompt as prompt_analista,
)
from limen.agents.llm_factory.base import ChatClient
from limen.core.models.context import AggregateAssessment
from limen.core.models.hazard import HazardType
from limen.core.models.risk import FireWeatherState, RiskLevel
from tests.factories import flood_record, wildfire_record


class _Registra:
    """Un client che registra i messaggi e risponde sempre uguale."""

    def __init__(self, risposta: str) -> None:
        self.risposta = risposta
        self.messaggi: list[Any] = []

    async def chat(self, messages: list[Any], **_: Any) -> str:
        self.messaggi.append(messages)
        return self.risposta


def _alluvione() -> AggregateAssessment:
    cella = flood_record(
        "c1", score=0.75, level=RiskLevel.VeryHigh, susceptibility=0.8, pluvial=0.94
    )
    cella = cella.model_copy(
        update={"breakdown": cella.breakdown.model_copy(update={"rain_mm": 111.7})}
    )
    return AggregateAssessment(
        aoi_id="it-friuli-venezia-giulia",
        hazard_type=HazardType.FLOOD,
        model_version="flood-v1",
        valuation_time=datetime(2026, 10, 6, 7, 0, tzinfo=UTC),
        n_cells=1,
        cells_high_or_above=1,
        cells_by_level={"VeryHigh": 1},
        top_cells=[cella],
    )


def test_ogni_pericolo_ha_il_suo_prompt() -> None:
    assert "alluvione" in prompt_briefing(HazardType.FLOOD)
    assert "72 ore" in prompt_briefing(HazardType.FLOOD)
    assert "potenziale" in prompt_briefing(HazardType.WILDFIRE)
    assert "frane" in prompt_briefing(HazardType.LANDSLIDE)
    assert "pluvial_rain" in prompt_analista(HazardType.FLOOD)
    assert "fire_weather" in prompt_analista(HazardType.WILDFIRE)


def test_i_dati_grezzi_arrivano_al_modello_per_pericolo() -> None:
    [cella] = _alluvione().top_cells
    assert "pioggia_prevista_72h_mm=112" in _note_pericolo(cella)
    # Fiume non noto: «n.d.», non uno zero che si leggerebbe «fiume basso».
    assert "portata_su_piena_ordinaria=n.d." in _note_pericolo(cella)
    fuoco = wildfire_record(
        "c2",
        score=0.69,
        level=RiskLevel.High,
        fwi_norm=0.72,
        fuel=1.0,
        fire_weather=FireWeatherState(
            day=date(2026, 10, 2), ffmc=91.0, dmc=92.0, dc=543.1, isi=10.5, bui=129.2, fwi=36.23
        ),
    )
    assert _note_pericolo(fuoco) == " fwi=36.2 dc=543"


async def test_il_briefing_dell_alluvione_usa_il_suo_prompt() -> None:
    client = _Registra("parola " * 200)
    await BriefingAgent(cast(ChatClient, client)).brief(_alluvione())
    sistema, utente = client.messaggi[0][0].content, client.messaggi[0][1].content
    assert "alluvione" in sistema
    assert "Pericolo: flood" in utente
    assert "pioggia_prevista_72h_mm=112" in utente


async def test_l_analista_accetta_le_cause_dell_alluvione() -> None:
    risposta = (
        '{"driver": "pluvial_rain", "anomalies": [], '
        '"attention_window_hours": 72, "confidence": 0.6}'
    )
    client = _Registra(risposta)
    analisi = await RiskAnalystAgent(cast(ChatClient, client)).analyse(_alluvione())
    assert analisi.driver == "pluvial_rain"
    assert "pluvial_rain" in client.messaggi[0][0].content


def test_il_ripiego_ha_la_causa_del_suo_pericolo() -> None:
    assert _neutral_fallback("x", HazardType.FLOOD).driver == "hydraulic_susceptibility"
    assert _neutral_fallback("x", HazardType.WILDFIRE).driver == "fuel_load"
    assert _neutral_fallback("x").driver == "static_susceptibility"
    assert isinstance(_neutral_fallback("x"), RiskAnalysis)


def test_il_testo_deterministico_parla_del_pericolo_giusto() -> None:
    comune = {
        "aoi_id": "it-x",
        "n_cells": 10,
        "cells_by_level": {"High": 2},
        "dominant_level": "High",
    }
    alluvione = deterministic_briefing(**comune, hazard=HazardType.FLOOD)
    incendio = deterministic_briefing(**comune, hazard=HazardType.WILDFIRE)
    frane = deterministic_briefing(**comune)
    assert "72 ore" in alluvione and "Caine" not in alluvione
    assert "potenziale" in incendio and "IFFI" not in incendio
    assert "Caine" in frane
