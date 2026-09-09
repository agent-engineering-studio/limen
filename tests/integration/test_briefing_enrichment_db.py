"""Il briefing asincrono non tocca i numeri (#78).

`test_llm_does_not_change_numeric_breakdown` prova l'invariante dentro il
workflow, dove l'LLM annota un contesto in memoria. Dopo #78 la narrativa
arriva **dopo**, con un UPDATE su righe già persistite: è un secondo modo di
violare la stessa invariante, e stavolta su disco. Qui si prova che l'UPDATE
tocca solo `explanation`.
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
from limen.core.models.hazard import DEFAULT_HAZARD
from limen.data.db import acquire, get_pool
from limen.data.repos import assessment_repo
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


@pytest.fixture()
async def seeded(reset_db: None) -> AsyncIterator[None]:
    async with acquire() as conn:
        await _seed(conn)
    yield


async def test_the_summary_is_rebuilt_from_the_persisted_rows(seeded: None) -> None:
    """Nessun `MonitoringContext` sopravvive fino al tick di arricchimento: le
    righe persistite *sono* la valutazione."""
    assessment = await assessment_repo.summary_by_run(_RUN_ID)
    assert assessment is not None
    assert assessment.aoi_id == _AOI_ID
    assert assessment.n_cells == 2
    assert assessment.cells_by_level == {"VeryHigh": 1, "Moderate": 1}
    assert assessment.cells_high_or_above == 1
    # Ordinate per punteggio: il prompt del briefing legge le prime.
    assert [c.cell_id for c in assessment.top_cells] == ["brief-cell-1", "brief-cell-2"]
    assert assessment.briefing_it is None


async def test_attaching_the_narrative_leaves_every_number_untouched(seeded: None) -> None:
    async with acquire() as conn:
        before = await conn.fetch(
            "SELECT cell_id, score, class, factors, computed_at "
            "FROM risk_assessments WHERE run_id = $1 ORDER BY cell_id",
            _RUN_ID,
        )

    rows = await assessment_repo.attach_narrative(
        _RUN_ID,
        briefing_it="Testo narrativo di prova.",
        analysis={
            "driver": "rain",
            "anomalies": [],
            "attention_window_hours": 24,
            "confidence": 0.7,
        },
    )
    assert rows == 2

    async with acquire() as conn:
        after = await conn.fetch(
            "SELECT cell_id, score, class, factors, computed_at, explanation "
            "FROM risk_assessments WHERE run_id = $1 ORDER BY cell_id",
            _RUN_ID,
        )

    for old, new in zip(before, after, strict=True):
        assert new["score"] == old["score"]
        assert new["class"] == old["class"]
        assert new["factors"] == old["factors"]
        assert new["computed_at"] == old["computed_at"]

    explanation = await _explanation(after[0])
    assert explanation["briefing_it"] == "Testo narrativo di prova."
    assert explanation["analysis"]["driver"] == "rain"
    # Fusione, non sostituzione: quello che lo sweep aveva scritto resta.
    assert explanation["model_version"] == "v1-test"


async def test_a_second_pass_sees_the_briefing_already_there(seeded: None) -> None:
    """Il job salta uno sweep già arricchito: la metrica in `job_runs` dice
    com'era finito lo sweep, non com'è la riga adesso."""
    await assessment_repo.attach_narrative(_RUN_ID, briefing_it="Primo testo.", analysis=None)
    assessment = await assessment_repo.summary_by_run(_RUN_ID)
    assert assessment is not None
    assert assessment.briefing_it == "Primo testo."


async def test_an_unknown_run_is_not_an_error(seeded: None) -> None:
    """Retention può aver droppato la partizione: nessuna riga, nessun crash."""
    assert await assessment_repo.summary_by_run(1) is None


async def _explanation(row: asyncpg.Record) -> dict[str, object]:
    value = row["explanation"]
    return dict(json.loads(value)) if isinstance(value, str) else dict(value)


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
    await assessment_repo.attach_narrative(
        _RUN_ID, briefing_it="Narrativa vera del modello.", analysis=None
    )
    body = (await client.get(f"/api/aoi/{_AOI_ID}/risk/latest")).json()
    assert body["briefing_is_fallback"] is False
    assert body["briefing_it"] == "Narrativa vera del modello."
