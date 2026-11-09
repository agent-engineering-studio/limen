"""CAP 1.2 (#499) e OGC API Features (#503) sulle righe vere di mv_comune_risk."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator

import httpx
import pytest

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.main import build_app_with_deps
from limen.config.settings import Settings
from limen.core.standard.cap import NS
from limen.data.db import acquire, get_pool
from limen.integrations._http import SharedHttpClient

pytestmark = pytest.mark.integration

_ATOM = "{http://www.w3.org/2005/Atom}"


async def _seed() -> None:
    async with acquire() as conn:
        await conn.execute("UPDATE hazards SET enabled = (hazard IN ('landslide', 'flood'))")
        await conn.execute(
            "INSERT INTO aoi (id, name, geom) VALUES ('it-std','Std', "
            "ST_Multi(ST_GeomFromText('POLYGON((10 40,10 42,12 42,12 40,10 40))',4326)))"
        )
        celle = [(10.5, "landslide", "VeryHigh", 0.91), (11.5, "landslide", "Low", 0.2)]
        celle += [(10.5, "flood", "Low", 0.1), (11.5, "flood", "Low", 0.1)]
        for i, (x, hazard, cls, score) in enumerate(celle):
            cid = f"it-std|0|{int(x)}"
            if hazard == "landslide":
                await conn.execute(
                    "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) "
                    "VALUES ($1,'it-std',0,$2, ST_GeomFromText($3,4326), 1.0)",
                    cid,
                    i,
                    f"POLYGON(({x} 40.4,{x} 40.6,{x + 0.1} 40.6,{x + 0.1} 40.4,{x} 40.4))",
                )
            await conn.execute(
                "INSERT INTO risk_assessments (cell_id, hazard_type, score, class, factors, "
                "computed_at, horizon, pipeline_version) "
                "VALUES ($1,$2::hazard_type,$3,$4,'{}'::jsonb, now(), 'now','v1')",
                cid,
                hazard,
                score,
                cls,
            )
        await conn.execute(
            "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES "
            "('099001','Primo','it-std', "
            "ST_Multi(ST_GeomFromText('POLYGON((10 40,10 41,11 41,11 40,10 40))',4326))), "
            "('099002','Secondo','it-std', "
            "ST_Multi(ST_GeomFromText('POLYGON((11 40,11 41,12 41,12 40,11 40))',4326)))"
        )
        await conn.execute(
            "INSERT INTO cell_comune (cell_id, istat_code) "
            "SELECT g.id, c.istat_code FROM grid_cells g JOIN comuni c "
            "ON ST_Contains(c.geom, g.centroid)"
        )
        await conn.execute("SELECT rebuild_latest_risk()")
        await conn.execute("SELECT refresh_mv_latest_risk()")


@pytest.fixture
async def client(reset_db: None, pg_pool: object) -> AsyncIterator[httpx.AsyncClient]:
    await _seed()
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=Settings.model_validate({"enable_insitu": False}),
        llm_factory=StubLlmClientFactory(),
    )
    app = build_app_with_deps(deps)
    app.state.deps = deps
    app.state.ready = True
    app.state.ready_detail = "test wiring"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    await SharedHttpClient.aclose()


async def test_feed_cap_porta_solo_il_comune_in_allerta(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/cap")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/atom+xml")
    feed = ET.fromstring(r.content)
    entries = feed.findall(f"{_ATOM}entry")
    assert [e.findtext(f"{_ATOM}title") for e in entries] == ["Pericolo di frana (Limen): Primo"]
    link = entries[0].find(f"{_ATOM}link")
    assert link is not None
    href = link.get("href") or ""
    assert href.startswith("http://test/api/cap/limen-landslide-099001-")

    m = await client.get(href.removeprefix("http://test"))
    assert m.status_code == 200
    assert m.headers["content-type"] == "application/cap+xml"
    alert = ET.fromstring(m.content)
    assert alert.findtext(f"{{{NS}}}status") == "Exercise"
    assert alert.findtext(f"{{{NS}}}info/{{{NS}}}severity") == "Severe"
    assert alert.findtext(f"{{{NS}}}info/{{{NS}}}area/{{{NS}}}geocode/{{{NS}}}value") == "099001"

    # Un identificativo di un calcolo vecchio non vale più.
    vecchio = href.removeprefix("http://test").rsplit("-", 1)[0] + "-20000101T000000"
    assert (await client.get(vecchio)).status_code == 404
    assert (await client.get("/api/cap/qualcosa")).status_code == 404


async def test_ogc_collezioni_e_oggetti(client: httpx.AsyncClient) -> None:
    landing = (await client.get("/api/ogc")).json()
    assert {link["rel"] for link in landing["links"]} >= {"conformance", "data", "service-desc"}
    conf = (await client.get("/api/ogc/conformance")).json()["conformsTo"]
    assert "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core" in conf

    cols = (await client.get("/api/ogc/collections")).json()["collections"]
    assert [c["id"] for c in cols] == ["comuni-flood", "comuni-landslide"]
    flood = next(c for c in cols if c["id"] == "comuni-flood")
    assert "Copernicus Emergency Management Service" in flood["attribution"]
    # Un pericolo non abilitato non è una collezione.
    assert (await client.get("/api/ogc/collections/comuni-wildfire")).status_code == 404

    r = await client.get("/api/ogc/collections/comuni-landslide/items?limit=1")
    assert r.headers["content-type"] == "application/geo+json"
    pagina = r.json()
    assert (pagina["numberMatched"], pagina["numberReturned"]) == (2, 1)
    assert pagina["features"][0]["id"] == "099001"
    assert pagina["features"][0]["properties"]["worst_class"] == "VeryHigh"
    succ = next(link["href"] for link in pagina["links"] if link["rel"] == "next")
    assert succ.endswith("limit=1&offset=1")
    seconda = (await client.get(succ.removeprefix("http://test"))).json()
    assert [f["id"] for f in seconda["features"]] == ["099002"]

    dentro = (
        await client.get("/api/ogc/collections/comuni-landslide/items?bbox=11.2,40.2,11.8,40.8")
    ).json()
    assert [f["id"] for f in dentro["features"]] == ["099002"]
    futuro = (
        await client.get(
            "/api/ogc/collections/comuni-landslide/items?datetime=2999-01-01T00:00:00Z/.."
        )
    ).json()
    assert futuro["numberMatched"] == 0
    assert (
        await client.get("/api/ogc/collections/comuni-landslide/items?bbox=1,2,3")
    ).status_code == 400

    uno = await client.get("/api/ogc/collections/comuni-landslide/items/099002")
    assert uno.json()["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert (
        await client.get("/api/ogc/collections/comuni-landslide/items/000000")
    ).status_code == 404
