"""La previsione entra nella riga del comune (#147).

Stava in un pannello a parte, per regione: «nessuna regione prevista sopra
soglia» è una risposta, ma non dice se il *tuo* comune sta salendo. Questi
test fissano come la riga compone il futuro — e le due cose che è facile
sbagliare: l'attenzione prevista si calcola con la stessa regola di quella di
adesso, e l'assenza di una riga previsionale non è un comune ignoto.
"""

from __future__ import annotations

from typing import Any

import pytest

from limen.cli.worker import _publish_next_fire
from limen.data.repos.comune_risk import _con_previsione


def _riga() -> dict[str, Any]:
    return {"istat_code": "078078", "name": "Marzi", "attention": 1.2}


def test_l_attenzione_prevista_usa_la_regola_di_adesso() -> None:
    # Due pericoli previsti oltre Moderato: il massimo più l'incremento del
    # 15 %, come per l'adesso. Numeri composti con regole diverse non si
    # confronterebbero, e il confronto è il punto.
    riga = _con_previsione(
        _riga(),
        {
            "landslide": {"class": "High", "score": 0.6, "priority": 1.2},
            "wildfire": {"class": "Moderate", "score": 0.4, "priority": 0.8},
        },
    )
    assert riga["forecast_attention"] == pytest.approx(1.2 * 1.15)
    assert riga["attention"] == 1.2


def test_nessuna_riga_previsionale_non_e_un_numero_inventato() -> None:
    # Lo stato previsionale tiene solo le celle da Moderato in su: senza
    # righe il comune è previsto sotto soglia, e non c'è un'attenzione da
    # mostrare. `None`, non zero.
    riga = _con_previsione(_riga(), {})
    assert riga["forecast"] == {}
    assert riga["forecast_attention"] is None


class _Schedule:
    def __init__(self, sid: str, quando: Any) -> None:
        self.id = sid
        self.next_fire_time = quando


class _Scheduler:
    def __init__(self, schedules: list[_Schedule]) -> None:
        self._s = schedules

    async def get_schedules(self) -> list[_Schedule]:
        return self._s


@pytest.mark.asyncio
async def test_il_worker_pubblica_il_prossimo_scatto(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'API non vede lo scheduler, che vive in memoria nel worker.

    Dedurre il prossimo calcolo dall'ultimo (`started_at + intervallo`)
    sbaglia proprio dopo un riavvio — quando `_deferred_interval` sposta il
    primo scatto a un intervallo dal boot. Quindi lo pubblica il worker.
    """
    from datetime import UTC, datetime

    scritti: list[tuple[str, Any, int]] = []

    class _Cache:
        async def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
            scritti.append((key, value, ttl_seconds))

    monkeypatch.setattr("limen.data.caching.postgres_cache.PostgresCache", _Cache)
    quando = datetime(2026, 9, 30, 12, 59, tzinfo=UTC)

    await _publish_next_fire(
        _Scheduler([_Schedule("limen-forecast-monitoring", quando), _Schedule("fermo", None)]),
        period=60,
    )

    (chiave, valore, ttl) = scritti[0]
    assert chiave == "scheduler:next_fire"
    assert valore == {"limen-forecast-monitoring": quando.isoformat()}
    # Scade: se il worker muore, l'API deve dire «non lo so», non contare
    # alla rovescia verso un calcolo che nessuno farà.
    assert ttl >= 180


@pytest.mark.asyncio
async def test_un_errore_di_cache_non_ferma_il_battito(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Rotta:
        async def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
            raise ConnectionError("database giù")

    monkeypatch.setattr("limen.data.caching.postgres_cache.PostgresCache", _Rotta)
    # Non solleva: il battito è ciò che dice che il worker è vivo, e non può
    # morire per colpa di un timer.
    await _publish_next_fire(_Scheduler([]), period=60)


def test_una_riga_storica_senza_catena_fwi_non_e_misurata() -> None:
    """Il 28-29 settembre ogni cella incendio scrisse 0,00 per assenza di
    catena, con `measured` ancora NULL. Per la mappa quel NULL vale
    «misurato»; per un grafico disegna una caduta a zero mai avvenuta. Il
    breakdown tiene il segnale grezzo e sa la differenza."""
    from limen.data.repos.comune_risk import _misurata

    senza_catena = {
        "fwi_norm": 0.0,
        "fuel": 1.0,
        "slope": 0.6,
        "spinup": True,
        "fire_weather": None,
    }
    assert _misurata("wildfire", senza_catena) is False


def test_una_giornata_asciutta_misurata_resta_misurata() -> None:
    # Pioggia 0,0 mm arrivata davvero: la cella è calma, non ignota.
    from limen.data.repos.comune_risk import _misurata

    asciutta = {
        "susceptibility": 0.4,
        "pluvial": 0.0,
        "fluvial": 0.0,
        "mapped": True,
        "rain_mm": 0.0,
        "discharge_ratio": None,
    }
    assert _misurata("flood", asciutta) is True


def test_fattori_illeggibili_non_diventano_un_buco() -> None:
    # «Non lo so» resta «non lo so»: senza poter leggere il breakdown non si
    # toglie un punto dal grafico.
    from limen.data.repos.comune_risk import _misurata

    assert _misurata("wildfire", "{non json") is True
    assert _misurata("wildfire", None) is True


@pytest.mark.asyncio
async def test_la_previsione_notturna_gira_per_ogni_pericolo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Girava solo per le frane: la colonna mostrava il futuro di un pericolo
    su tre. E un pericolo che fallisce non ferma gli altri — le frane non
    devono saltare perché GloFAS ha risposto 429."""
    from types import SimpleNamespace
    from typing import cast

    from limen.api.dependencies import AppDependencies
    from limen.api.jobs import forecast_history as job
    from limen.core.models.hazard import HazardType

    visti: list[HazardType] = []

    async def _corsa(*, settings: Any, hazard: HazardType) -> int:
        visti.append(hazard)
        if hazard is HazardType.FLOOD:
            raise RuntimeError("429 Too Many Requests")
        return 10

    monkeypatch.setattr(job, "run_forecast_history", _corsa)
    deps = SimpleNamespace(
        settings=SimpleNamespace(
            hazards=SimpleNamespace(
                enabled=[HazardType.LANDSLIDE, HazardType.FLOOD, HazardType.WILDFIRE]
            )
        )
    )

    totale = await job.run_forecast_history_job(cast("AppDependencies", deps))

    assert visti == [HazardType.LANDSLIDE, HazardType.FLOOD, HazardType.WILDFIRE]
    assert totale == 20


@pytest.mark.asyncio
async def test_una_corsa_a_zero_celle_resta_una_corsa(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una giornata asciutta: l'alluvione è prevista sotto soglia ovunque e
    non lascia righe. Dedurre la corsa dalle righe la farebbe sparire, e la
    testata direbbe «non disponibile» di un pericolo appena calcolato."""
    from limen.agents.workflows import forecast_history as fh
    from limen.core.models.hazard import HazardType

    scritti: dict[str, Any] = {}

    class _Cache:
        async def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
            scritti[key] = value

    monkeypatch.setattr("limen.data.caching.postgres_cache.PostgresCache", _Cache)
    await fh._registra_corsa(HazardType.FLOOD, 0)

    registrata = scritti["forecast:last_run:flood"]
    assert registrata["cells"] == 0
    assert isinstance(registrata["run_at"], str)


def test_i_segnali_della_pioggia_vanno_solo_all_alluvione() -> None:
    """Sotto soglia l'alluvione resta 0,00 per settimane: pioggia prevista e
    soglia sono ciò che dice quanto manca. Solo a lei — frane e incendio
    hanno un punteggio continuo, e quei campi non vi significherebbero niente."""
    from limen.data.repos.comune_risk import _con_segnali

    riga = {
        "hazards": {
            "landslide": {"class": "Moderate", "score": 0.37},
            "flood": {"class": "None", "score": 0.0},
        }
    }
    segnali = {"rain_mm": 18.4, "rain_threshold_mm": 40.0, "discharge_known": False}

    _con_segnali(riga, segnali)

    assert riga["hazards"]["flood"]["rain_mm"] == 18.4
    assert riga["hazards"]["flood"]["discharge_known"] is False
    assert "rain_mm" not in riga["hazards"]["landslide"]


def test_senza_segnali_la_riga_non_cambia() -> None:
    from limen.data.repos.comune_risk import _con_segnali

    riga = {"hazards": {"flood": {"class": "None", "score": 0.0}}}
    _con_segnali(riga, None)
    assert riga["hazards"]["flood"] == {"class": "None", "score": 0.0}


def test_la_previsione_per_comune_tiene_anche_lo_zero() -> None:
    """Il 30 settembre l'alluvione è uscita sotto soglia ovunque: tenendo solo
    le celle da Moderato in su non restava una riga, e il grafico non aveva
    tratteggio. Qui ogni comune ha la sua previsione, anche a 0,00."""
    from types import SimpleNamespace

    from limen.agents.workflows.forecast_history import per_comune
    from limen.core.models.risk import FloodBreakdown, RiskLevel

    def cella(cid: str, score: float, pioggia: float | None) -> Any:
        return SimpleNamespace(
            cell_id=cid,
            score=score,
            level=RiskLevel.None_,
            breakdown=FloodBreakdown(susceptibility=0.4, pluvial=0.0, fluvial=0.0, rain_mm=pioggia),
        )

    out = per_comune(
        [cella("a", 0.0, 3.2), cella("b", 0.0, 12.6), cella("c", 0.0, None)],
        {"a": "065001", "b": "065001", "c": "065002"},
    )

    # Zero, ma c'è: e con la pioggia più alta fra le celle del comune.
    assert out["065001"] == (0.0, "None", 12.6)
    assert out["065002"] == (0.0, "None", None)


def test_le_celle_senza_comune_restano_fuori() -> None:
    from types import SimpleNamespace

    from limen.agents.workflows.forecast_history import per_comune
    from limen.core.models.risk import (
        ComponentBreakdown,
        MeteoBreakdown,
        RiskLevel,
        StaticBreakdown,
    )

    frana = ComponentBreakdown(
        s=0.5,
        m=0.1,
        e=0.0,
        f=0.0,
        h=0.0,
        static_terms=StaticBreakdown(
            susc_ispra=0.5, iffi_density=0.1, slope=0.5, pai=0.5, litho_weight=0.5
        ),
        meteo_terms=MeteoBreakdown(
            caine_excess=0.0, caine_norm=0.0, api_factor=0.0, soil_factor=0.5
        ),
    )
    cella: Any = SimpleNamespace(
        cell_id="mare", score=0.4, level=RiskLevel.Moderate, breakdown=frana
    )
    assert per_comune([cella], {}) == {}


def test_il_confronto_col_mese_va_solo_all_incendio() -> None:
    """Le classi dell'incendio sono assolute: FWI e percentile del mese dicono
    se il numero è insolito per la stagione, senza toccare il punteggio."""
    from limen.data.repos.comune_risk import _con_segnali

    riga = {
        "hazards": {
            "landslide": {"class": "Moderate", "score": 0.37},
            "wildfire": {"class": "High", "score": 0.49},
        }
    }
    incendio = {"fwi": 23.7, "fwi_month": 10, "fwi_percentile": 96}

    _con_segnali(riga, None, incendio)

    assert riga["hazards"]["wildfire"]["fwi_percentile"] == 96
    assert riga["hazards"]["wildfire"]["score"] == 0.49
    assert "fwi" not in riga["hazards"]["landslide"]
