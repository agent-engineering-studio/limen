"""Parametro hazard sulle superfici HTTP (issue #86).

Il criterio di #57 è la retrocompatibilità: **senza il parametro la risposta
è identica** a quella con il pericolo di default esplicito. E i due modi di
sbagliare devono comportarsi in modo diverso: un nome ignoto è un errore del
client (422), un pericolo valido ma non abilitato è una risposta vuota
coerente, perché un client non ha modo di sapere in anticipo cosa questo
deployment valuta.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.main import build_app_with_deps
from limen.config.settings import Settings
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire, get_pool
from limen.integrations._http import SharedHttpClient

pytestmark = pytest.mark.integration

_PARAMETERISED = (
    "/api/aoi/it-test/risk/latest",
    "/api/cell/it-test%7C0%7C0/breakdown",
    "/api/cell/it-test%7C0%7C0/history",
    "/api/alerts",
    "/api/alerts/forecast",
    "/api/legend",
)


@pytest.fixture
async def client(reset_db: None, pg_pool: object) -> AsyncIterator[httpx.AsyncClient]:
    # `hazards` non è in reset_db: senza questo, lo stato globale della
    # tabella dipenderebbe dall'ordine dei moduli di test.
    async with acquire() as conn:
        await conn.execute("UPDATE hazards SET enabled = (hazard = 'landslide')")
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=Settings.model_validate({"enable_insitu": False}),
        llm_factory=StubLlmClientFactory(),
    )
    app = build_app_with_deps(deps)
    # ASGITransport does not fire the lifespan; the production path is covered
    # in test_api_lifespan.py.
    app.state.deps = deps
    app.state.ready = True
    app.state.ready_detail = "test wiring"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await SharedHttpClient.aclose()


@pytest.mark.parametrize("path", _PARAMETERISED)
async def test_unknown_hazard_is_a_client_error(client: httpx.AsyncClient, path: str) -> None:
    """FastAPI valida l'enum, quindi non serve un controllo scritto a mano e
    un nome sbagliato non diventa un errore del server."""
    assert (await client.get(f"{path}?hazard=pippo")).status_code == 422


@pytest.mark.parametrize("path", ["/api/alerts", "/api/alerts/forecast", "/api/legend"])
async def test_omitting_the_parameter_matches_the_explicit_default(
    client: httpx.AsyncClient, path: str
) -> None:
    without = await client.get(path)
    explicit = await client.get(f"{path}?hazard={DEFAULT_HAZARD.value}")
    assert without.status_code == explicit.status_code == 200
    assert without.json() == explicit.json()


async def test_a_valid_but_disabled_hazard_returns_empty_not_an_error(
    client: httpx.AsyncClient,
) -> None:
    res = await client.get(f"/api/alerts?hazard={HazardType.FLOOD.value}")
    assert res.status_code == 200
    assert res.json()["items"] == []

    forecast = await client.get(f"/api/alerts/forecast?hazard={HazardType.FLOOD.value}")
    assert forecast.status_code == 200
    assert forecast.json()["items"] == []


async def test_hazards_endpoint_lists_only_the_enabled_ones(
    client: httpx.AsyncClient,
) -> None:
    """Legge la tabella `hazards`, non `HAZARDS__ENABLED`: la tabella è quella
    che `mv_latest_risk` incrocia, quindi è la lista per cui un client può
    davvero ottenere dati."""
    res = await client.get("/api/hazards")
    assert res.status_code == 200
    body = res.json()
    assert body["default"] == DEFAULT_HAZARD.value
    assert {item["hazard"] for item in body["items"]} == {DEFAULT_HAZARD.value}
    assert all(item["label_it"] for item in body["items"])
    # Serve al selettore della SPA a ogni caricamento.
    assert "max-age" in res.headers.get("Cache-Control", "")


async def test_alerts_carry_the_hazard_in_the_payload(client: httpx.AsyncClient) -> None:
    """Il DTO lo espone anche a lista vuota: il frontend di #87 lo legge per
    sapere cosa sta mostrando."""
    res = await client.get("/api/alerts")
    assert res.status_code == 200
    # La forma della risposta è stabile: nessuna chiave rimossa dal refactor.
    assert set(res.json()) == {"items"}


# ---------------------------------------------------------------------------
# Il filtro fa davvero il suo lavoro
# ---------------------------------------------------------------------------
async def _seed_two_hazard_rows() -> str:
    """Una cella con un assessment per pericolo, per provare il filtro.

    Senza una riga di un pericolo non-default, ogni query potrebbe tornare
    fissata sul default e la suite resterebbe verde: è il buco che questo
    test chiude.
    """
    aoi_id, cell_id = "hz-api-aoi", "hz-api-cell"
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aoi (id, name, kind, geom)
            VALUES ($1, 'Hazard API', 'region',
                    ST_Multi(ST_MakeEnvelope(16.8, 41.1, 16.9, 41.2, 4326)))
            ON CONFLICT (id) DO NOTHING
            """,
            aoi_id,
        )
        await conn.execute(
            """
            INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
            VALUES ($1, $2, 0, 0,
                    ST_MakeEnvelope(16.81, 41.11, 16.82, 41.12, 4326), 1.0)
            ON CONFLICT (id) DO NOTHING
            """,
            cell_id,
            aoi_id,
        )
        for hazard, score, level in (
            (HazardType.LANDSLIDE, 0.91, "VeryHigh"),
            (HazardType.FLOOD, 0.42, "Moderate"),
        ):
            await conn.execute(
                """
                INSERT INTO risk_assessments (
                    cell_id, hazard_type, horizon, score, class,
                    factors, pipeline_version
                ) VALUES ($1, $2, '24h', $3, $4, '{}'::jsonb, 'test')
                """,
                cell_id,
                hazard.value,
                score,
                level,
            )
    return cell_id


async def test_the_filter_selects_the_requested_hazard(client: httpx.AsyncClient) -> None:
    """Due assessment sulla stessa cella, uno per pericolo: ogni endpoint deve
    restituire quello chiesto, non sempre il default."""
    cell_id = await _seed_two_hazard_rows()
    quoted = cell_id.replace("|", "%7C")

    default = await client.get(f"/api/cell/{quoted}/breakdown")
    assert default.status_code == 200
    assert default.json()["hazard_type"] == DEFAULT_HAZARD.value
    assert default.json()["score"] == pytest.approx(0.91)

    flood = await client.get(f"/api/cell/{quoted}/breakdown?hazard={HazardType.FLOOD.value}")
    assert flood.status_code == 200
    assert flood.json()["hazard_type"] == HazardType.FLOOD.value
    assert flood.json()["score"] == pytest.approx(0.42)

    # Anche la serie storica: il filtro non è solo sul breakdown.
    hist = await client.get(f"/api/cell/{quoted}/history?hazard={HazardType.FLOOD.value}")
    assert hist.status_code == 200
    assert [p["score"] for p in hist.json()["observed"]] == [pytest.approx(0.42)]


async def test_alerts_of_a_hazard_without_a_yaml_degrade_instead_of_failing(
    client: httpx.AsyncClient,
) -> None:
    """Righe di alluvione esistono ma `hazards/flood.yaml` no: l'elenco resta
    corretto, ordinato per solo punteggio, invece di diventare un 500.
    Sopprimerlo sarebbe peggio che ordinarlo meno bene."""
    await _seed_two_hazard_rows()
    res = await client.get(f"/api/alerts?hazard={HazardType.FLOOD.value}&threshold=Moderate")
    assert res.status_code == 200
    items = res.json()["items"]
    assert [i["hazard_type"] for i in items] == [HazardType.FLOOD.value]
    # Esposizione neutra ⇒ priorità uguale al punteggio.
    assert items[0]["priority"] == pytest.approx(items[0]["score"])
