"""La versione inglese delle spiegazioni regionali (migrazione 073).

L'inglese è la traduzione del racconto italiano, e si salva solo se porta gli
stessi numeri: un valore cambiato è l'unico guasto che un lettore non vede.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from limen.agents.chat_agents.briefing import deterministic_briefing
from limen.agents.chat_agents.traduttore import TraduttoreRacconti, numeri, numeri_coincidono
from limen.api.jobs import briefing_enrichment as be
from limen.core.models.hazard import HazardType
from limen.data.repos.spiegazioni_repo import Spiegazione

_IT = "Su 23.214 aree, 57 sono in classe alta; il punteggio massimo è 0,45 nelle prossime 72 ore."
_EN = "Of 23,214 areas, 57 are in the high class; the highest score is 0.45 over the next 72 hours."


def _risposta(testo: str, anomalies: list[str]) -> str:
    return json.dumps({"testo": testo, "anomalies": anomalies})


def test_i_numeri_si_leggono_con_le_convenzioni_della_lingua() -> None:
    assert numeri(_IT, "it") == [Decimal("23214"), Decimal("57"), Decimal("0.45"), Decimal("72")]
    assert numeri(_EN, "en") == numeri(_IT, "it")


def test_i_racconti_italiani_col_punto_decimale_coincidono() -> None:
    """Visto in produzione il 12 ottobre 2026: 17 traduzioni su 20 scartate
    perché l'AI scrive i punteggi italiani col punto (`0.374`) e «combustibile
    1.000» per 1,0, e il primo controllo li leggeva come migliaia."""
    it = "FWI costante a 0.374, pendenza 0.549-0.661, combustibile 1.000, 14.078 celle."
    en = "FWI constant at 0.374, slope 0.549-0.661, fuel 1, 14,078 cells."
    assert numeri_coincidono(it, en)
    assert not numeri_coincidono(it, en.replace("0.374", "0.375"))


def test_un_numero_cambiato_aggiunto_o_perso_non_coincide() -> None:
    assert numeri_coincidono(_IT, _EN)
    assert not numeri_coincidono(_IT, _EN.replace("57", "58"))
    assert not numeri_coincidono(_IT, _EN + " In 2024.")
    assert not numeri_coincidono(_IT, _EN.replace(" over the next 72 hours", ""))


class _Client:
    def __init__(self, risposta: str | Exception) -> None:
        self.risposta = risposta
        self.messaggi: list[Any] = []

    async def chat(self, messages: Any, **_kw: Any) -> str:
        self.messaggi.append(messages)
        if isinstance(self.risposta, Exception):
            raise self.risposta
        return self.risposta


async def test_una_traduzione_fedele_si_accetta_con_le_anomalie() -> None:
    client = _Client(_risposta(_EN, ["2 isolated cells"]))
    out = await TraduttoreRacconti(client).traduci(_IT, ["2 celle isolate"])  # type: ignore[arg-type]  # finto con la sola chat
    assert out is not None
    assert out.testo == _EN
    assert out.anomalies == ["2 isolated cells"]


async def test_numeri_diversi_json_rotto_o_modello_giu_danno_none() -> None:
    sbagliata = _risposta(_EN.replace("0.45", "0.5"), [])
    for risposta in (sbagliata, "non è json", RuntimeError("gateway giù")):
        out = await TraduttoreRacconti(_Client(risposta)).traduci(_IT, [])  # type: ignore[arg-type]  # finto
        assert out is None
    # Anomalie perse per strada: la traduzione non è completa.
    persa = _risposta(_EN, [])
    assert await TraduttoreRacconti(_Client(persa)).traduci(_IT, ["2 celle"]) is None  # type: ignore[arg-type]  # finto


def test_il_testo_deterministico_ha_la_sua_versione_inglese() -> None:
    comune: dict[str, Any] = {
        "aoi_id": "it-puglia",
        "n_cells": 100,
        "cells_by_level": {"High": 3, "Low": 97},
        "dominant_level": "High",
    }
    for hazard in HazardType:
        en = deterministic_briefing(**comune, hazard=hazard, lingua="en")
        it = deterministic_briefing(**comune, hazard=hazard)
        assert en != it
        assert "without the narrative model" in en
        assert numeri_coincidono(it, en)


def _spiegazione() -> Spiegazione:
    return Spiegazione(
        aoi_id="it-puglia",
        hazard=HazardType.FLOOD,
        run_id=7,
        livello="High",
        scritta=datetime(2026, 10, 12, 8, tzinfo=UTC),
        modello="fast-cloud",
        ripiego=False,
        testo=_IT,
        analisi={"driver": "pluvial_rain", "anomalies": ["2 celle isolate"], "confidence": 0.7},
    )


class _Factory:
    def __init__(self, risposta: str) -> None:
        self.risposta = risposta

    def create(self, _role: str) -> _Client:
        return _Client(self.risposta)


class _Deps:
    def __init__(self, risposta: str) -> None:
        self.llm_factory = _Factory(risposta)


async def _prepara(monkeypatch: Any) -> list[dict[str, Any]]:
    scritte: list[dict[str, Any]] = []

    async def _da_tradurre(lingua: str, *, limite: int) -> list[Spiegazione]:
        assert lingua == "en"
        return [_spiegazione()]

    async def _scrivi(**kw: Any) -> None:
        scritte.append(kw)

    async def _summary(_aoi: str, _hazard: HazardType) -> None:
        return None

    monkeypatch.setattr(be.spiegazioni_repo, "da_tradurre", _da_tradurre)
    monkeypatch.setattr(be.spiegazioni_repo, "scrivi", _scrivi)
    monkeypatch.setattr(be.assessment_repo, "summary_for_region", _summary)
    return scritte


async def test_il_job_salva_la_traduzione_in_inglese(monkeypatch: Any) -> None:
    scritte = await _prepara(monkeypatch)
    risposta = _risposta(_EN, ["2 isolated cells"])
    assert await be._traduci(_Deps(risposta), "fast-cloud") == 1  # type: ignore[arg-type]  # finto
    (riga,) = scritte
    assert (riga["lingua"], riga["ripiego"], riga["testo"]) == ("en", False, _EN)
    assert riga["analisi"]["anomalies"] == ["2 isolated cells"]
    assert riga["analisi"]["driver"] == "pluvial_rain"
    assert riga["run_id"] == 7


async def test_una_traduzione_infedele_lascia_il_ripiego_inglese(monkeypatch: Any) -> None:
    """Non si riprova a ogni tick: la riga c'è, e si rifà quando l'italiano cambia."""
    scritte = await _prepara(monkeypatch)
    risposta = _risposta(_EN.replace("57", "75"), ["2 isolated cells"])
    assert await be._traduci(_Deps(risposta), "fast-cloud") == 0  # type: ignore[arg-type]  # finto
    (riga,) = scritte
    assert (riga["lingua"], riga["ripiego"], riga["analisi"]) == ("en", True, None)
    assert "without the narrative model" in riga["testo"]
