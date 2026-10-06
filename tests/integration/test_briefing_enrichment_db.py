"""La spiegazione asincrona: per regione, e senza toccare i numeri (#78).

Dopo #78 la narrativa arriva **dopo** lo sweep. Dalla migrazione 064 sta in
`spiegazioni_regione`, una tabella che lo sweep non tocca: prima finiva su
`latest_risk`, che lo sweep riscrive ogni ora, e spariva al giro dopo.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import httpx
import pytest

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.main import build_app_with_deps
from limen.config.settings import Settings
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire, get_pool
from limen.data.repos import assessment_repo, spiegazioni_repo
from limen.integrations._http import SharedHttpClient

pytestmark = pytest.mark.integration

#: La forma che `ComponentBreakdown.factors_payload()` scrive davvero. Un
#: dizionario inventato passerebbe l'INSERT e fallirebbe alla rilettura, che è
#: esattamente il difetto che questo test deve poter cogliere.
_FACTORS: dict[str, object] = {
    "s": 0.5,
    "m": 0.3,
    "e": 0.2,
    "f": 0.0,
    "h": 0.1,
    "static_terms": {
        "susc_ispra": 0.4,
        "iffi_density": 0.2,
        "slope": 0.3,
        "pai": 0.1,
        "litho_weight": 0.5,
    },
    "meteo_terms": {
        "caine_excess": 0.2,
        "caine_norm": 0.3,
        "api_factor": 0.6,
        "soil_factor": 0.7,
    },
}

_AOI_ID = "brief-test-aoi"
_CELLS = ("brief-cell-1", "brief-cell-2")
_RUN_ID = 987_654


async def _seed(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO aoi (id, name, kind, geom)
        VALUES ($1, 'Briefing test', 'region',
                ST_Multi(ST_MakeEnvelope(16.8, 41.1, 16.9, 41.2, 4326)))
        ON CONFLICT (id) DO NOTHING
        """,
        _AOI_ID,
    )
    for i, cell_id in enumerate(_CELLS):
        lon = 16.81 + i * 0.01
        await conn.execute(
            """
            INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
            VALUES ($1, $2, 0, $3,
                    ST_MakeEnvelope($4::float8, 41.11, $4::float8 + 0.01, 41.12, 4326), 1.0)
            ON CONFLICT (id) DO NOTHING
            """,
            cell_id,
            _AOI_ID,
            i,
            lon,
        )
    # Come le scrive lo sweep orario: `briefing_it` e `analysis` a NULL, e **un
    # solo `computed_at` per tutto lo sweep** — la COPY di #76 passa un istante
    # unico, e l'endpoint seleziona le righe del MAX(computed_at). Con un
    # `now()` per riga se ne vedrebbe una sola.
    computed_at = datetime.now(UTC)
    for cell_id, score, level in zip(_CELLS, (0.81, 0.42), ("VeryHigh", "Moderate"), strict=True):
        await conn.execute(
            """
            INSERT INTO risk_assessments (
                cell_id, computed_at, hazard_type, horizon, score, class,
                factors, explanation, pipeline_version, run_id
            ) VALUES ($1, $7, $2, '24h', $3, $4,
                      $6::jsonb,
                      jsonb_build_object(
                          'model_version', 'v1-test',
                          'valuation_time', $8::text,
                          'analysis', NULL,
                          'briefing_it', NULL
                      ),
                      'v1-deterministic', $5)
            """,
            cell_id,
            DEFAULT_HAZARD.value,
            score,
            level,
            _RUN_ID,
            json.dumps(_FACTORS),
            computed_at,
            computed_at.isoformat(),
        )
    # Lo stato corrente lo scrive il passo di persistenza (#125), che questo
    # test non esegue: qui le righe sono seminate a mano, quindi si
    # ricostruisce — è la stessa funzione che userebbe un operatore dopo un
    # ripristino.
    await conn.execute("SELECT rebuild_latest_risk()")


@pytest.fixture()
async def seeded(reset_db: None) -> AsyncIterator[None]:
    async with acquire() as conn:
        await _seed(conn)
    yield


async def _scrivi(testo: str, *, ripiego: bool = False) -> None:
    await spiegazioni_repo.scrivi(
        aoi_id=_AOI_ID,
        hazard=DEFAULT_HAZARD,
        run_id=_RUN_ID,
        livello="VeryHigh",
        modello="quality-cloud",
        ripiego=ripiego,
        testo=testo,
        analisi={
            "driver": "meteo_trigger",
            "anomalies": [],
            "attention_window_hours": 24,
            "confidence": 0.7,
        },
    )


async def test_the_summary_is_rebuilt_from_the_current_state(seeded: None) -> None:
    """Nessun `MonitoringContext` sopravvive fino al tick di arricchimento:
    lo stato corrente *è* la valutazione."""
    assessment = await assessment_repo.summary_for_region(_AOI_ID, DEFAULT_HAZARD)
    assert assessment is not None
    assert assessment.aoi_id == _AOI_ID
    assert assessment.n_cells == 2
    assert assessment.cells_by_level == {"VeryHigh": 1, "Moderate": 1}
    assert assessment.cells_high_or_above == 1
    # Ordinate per punteggio: il prompt del briefing legge le prime.
    assert [c.cell_id for c in assessment.top_cells] == ["brief-cell-1", "brief-cell-2"]


async def test_a_region_without_state_is_not_an_error(seeded: None) -> None:
    assert await assessment_repo.summary_for_region(_AOI_ID, HazardType.WILDFIRE) is None


async def test_writing_the_narrative_leaves_every_number_untouched(seeded: None) -> None:
    async with acquire() as conn:
        before = await conn.fetch(
            "SELECT cell_id, score, class, factors, computed_at FROM latest_risk ORDER BY cell_id"
        )
    await _scrivi("Testo narrativo di prova.")
    async with acquire() as conn:
        after = await conn.fetch(
            "SELECT cell_id, score, class, factors, computed_at FROM latest_risk ORDER BY cell_id"
        )
    assert [dict(r) for r in after] == [dict(r) for r in before]

    letta = await spiegazioni_repo.leggi(_AOI_ID, DEFAULT_HAZARD)
    assert letta is not None
    assert letta.testo == "Testo narrativo di prova."
    assert letta.analisi is not None and letta.analisi["driver"] == "meteo_trigger"


async def test_la_spiegazione_sopravvive_allo_sweep_successivo(seeded: None) -> None:
    """Il difetto della 064: lo sweep riscrive `latest_risk` per intero, e la
    spiegazione attaccata lì spariva al giro dopo."""
    await _scrivi("Scritta alle 12:05.")
    async with acquire() as conn:
        await conn.execute("SELECT rebuild_latest_risk()")
    letta = await spiegazioni_repo.leggi(_AOI_ID, DEFAULT_HAZARD)
    assert letta is not None and letta.testo == "Scritta alle 12:05."


@pytest.fixture
async def client(seeded: None) -> AsyncIterator[httpx.AsyncClient]:
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=Settings.model_validate({"enable_insitu": False}),
        llm_factory=StubLlmClientFactory(),
    )
    app = build_app_with_deps(deps)
    app.state.deps = deps
    app.state.ready = True
    app.state.ready_detail = "test wiring"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await SharedHttpClient.aclose()


async def test_the_api_shows_the_deterministic_text_while_the_briefing_is_pending(
    client: httpx.AsyncClient,
) -> None:
    """Un pannello vuoto sarebbe una regressione rispetto a prima della #78:
    lo sweep orario scrive `briefing_it` NULL per costruzione, e per le regioni
    non escalate resta NULL per sempre. Il flag dice che è un segnaposto, così
    la SPA non lo presenta come l'analisi."""
    resp = await client.get(f"/api/aoi/{_AOI_ID}/risk/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["briefing_is_fallback"] is True
    assert "modello deterministico Limen" in body["briefing_it"]
    # I numeri citati sono quelli delle righe, non inventati.
    assert f"Le celle valutate sono {len(_CELLS)}" in body["briefing_it"]


async def test_the_api_prefers_the_real_briefing_once_it_lands(
    client: httpx.AsyncClient,
) -> None:
    await _scrivi("Narrativa vera del modello.")
    body = (await client.get(f"/api/aoi/{_AOI_ID}/risk/latest")).json()
    assert body["briefing_is_fallback"] is False
    assert body["briefing_it"] == "Narrativa vera del modello."
    assert body["briefing_model"] == "quality-cloud"
    assert body["briefing_written_at"] is not None
    assert body["analysis"]["driver"] == "meteo_trigger"


async def test_un_ripiego_non_viene_attribuito_all_ai(client: httpx.AsyncClient) -> None:
    await _scrivi("Testo deterministico salvato.", ripiego=True)
    body = (await client.get(f"/api/aoi/{_AOI_ID}/risk/latest")).json()
    assert body["briefing_is_fallback"] is True
    assert body["briefing_model"] is None
    assert body["analysis"] is None


async def test_il_riassunto_vede_tutta_la_regione_non_solo_le_celle_del_run(seeded: None) -> None:
    """#155: lo sweep orario scrive solo le celle cambiate (#135). Un run che
    ha toccato una cella sola non deve far raccontare una regione di una
    cella: conteggi e celle peggiori vengono dallo stato attuale."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO risk_assessments (
                cell_id, computed_at, hazard_type, horizon, score, class,
                factors, explanation, pipeline_version, run_id
            ) VALUES ($1, now(), $2, '24h', 0.44, 'Moderate', $3::jsonb,
                      jsonb_build_object('model_version', 'v1-test'),
                      'v1-deterministic', $4)
            """,
            "brief-cell-2",
            DEFAULT_HAZARD.value,
            json.dumps(_FACTORS),
            _RUN_ID + 1,
        )
        await conn.execute("SELECT rebuild_latest_risk()")
    assessment = await assessment_repo.summary_for_region(_AOI_ID, DEFAULT_HAZARD)
    assert assessment is not None
    assert assessment.n_cells == 2
    assert assessment.cells_by_level == {"VeryHigh": 1, "Moderate": 1}
    assert assessment.top_cells[0].cell_id == "brief-cell-1"


async def test_la_spiegazione_della_regione_ha_il_suo_endpoint(client: httpx.AsyncClient) -> None:
    vuota = (await client.get(f"/api/aoi/{_AOI_ID}/spiegazione")).json()
    assert vuota["spiegazione"] is None
    await _scrivi("Scritta dal modello.")
    body = (await client.get(f"/api/aoi/{_AOI_ID}/spiegazione")).json()
    assert body["spiegazione"]["testo"] == "Scritta dal modello."
    assert body["spiegazione"]["modello"] == "quality-cloud"


async def test_la_provenienza_dice_lo_stato_vero(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/provenienza")).json()
    assert body["motore"] == "deterministic"
    assert body["sfidante_ml_attivo"] is False
    assert body["correttore_pioggia"]["stato"] == "raccolta_dati"
    assert body["correttore_pioggia"]["nodi_obiettivo"] == 150


async def test_recenti_conta_solo_le_spiegazioni_vere(seeded: None) -> None:
    await _scrivi("Scritta dal modello.")
    assert await spiegazioni_repo.recenti(12) == {(_AOI_ID, DEFAULT_HAZARD.value): "VeryHigh"}
    await _scrivi("Ripiego.", ripiego=True)
    assert await spiegazioni_repo.recenti(12) == {}
