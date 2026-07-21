# Comune/Region Risk Aggregation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Roll up per-cell risk to an administrative **comune** level (region already covered by `v_region_tiles`) — worst-cell headline + class profile + exposure-ranked leaderboard — and surface it on the map, sidebar, a leaderboard, REST, MCP/A2A, the static report, and alert enrichment.

**Architecture:** New `comuni` + `cell_comune` tables (seeded once from the GeoServer ISTAT boundaries) feed a `mv_comune_risk` materialized view mirroring `v_region_tiles`. Refresh is chained onto the existing `refresh_mv_latest_risk()` so every monitoring tick updates it. All consumers read the view; nothing runs cross-DB in the hot path.

**Tech Stack:** Python 3.12 + `uv`, asyncpg + PostGIS (no ORM), FastAPI, FastMCP, MapLibre + pg_tileserv, Vite/React/TS.

**Spec:** `docs/superpowers/specs/2026-07-21-comune-region-risk-aggregation-design.md`

---

## File Structure

- Create `src/limen/data/migrations/026_comuni.sql` — `comuni`, `cell_comune`, `mv_comune_risk`, extended refresh.
- Create `src/limen/cli/seed_comuni.py` + register in `src/limen/cli/main.py` — `limen seed-comuni`.
- Create `src/limen/data/repos/comune_risk.py` — read queries over `mv_comune_risk`.
- Create `src/limen/api/endpoints/comuni.py` + register in `src/limen/api/endpoints/__init__.py`.
- Modify `src/limen/mcp/tools.py` + `src/limen/mcp/server.py` — `comune_risk` / `top_comuni` tools.
- Modify `src/limen/a2a/skills.py` — `comune_risk` / `top_comuni` A2A skills.
- Modify `src/limen/report/builder.py` + `src/limen/report/render.py` + `templates/report.html.j2` — comuni section.
- Modify `src/limen/notifications/base.py` + `src/limen/agents/executors/alert_dispatch.py` — comune enrichment.
- Frontend: `frontend/src/components/RiskMap.tsx` (comune layer), `frontend/src/components/ComuneLeaderboard.tsx` (new), `frontend/src/components/RegionAccordion.tsx` (headline), `frontend/src/lib/api-client.ts`, `frontend/src/types.ts`, `frontend/src/App.tsx`.

---

## Task 1: Migration — comuni, cell_comune, mv_comune_risk, refresh

**Files:**
- Create: `src/limen/data/migrations/026_comuni.sql`
- Test: `tests/integration/test_comune_matview.py`

- [ ] **Step 1: Write the migration**

Create `src/limen/data/migrations/026_comuni.sql`:

```sql
-- Administrative comune boundaries (ISTAT) + cell→comune tag + comune rollup.
-- Boundaries are imported into the operational DB by `limen seed-comuni` so
-- nothing queries the GeoServer DB in the hot path. mv_comune_risk mirrors
-- v_region_tiles (migration 019) one level down: worst-cell class + counts.

CREATE TABLE IF NOT EXISTS comuni (
    istat_code text PRIMARY KEY,
    name       text NOT NULL,
    aoi_id     text NOT NULL REFERENCES aoi(id) ON DELETE CASCADE,
    geom       geometry(MultiPolygon, 4326) NOT NULL,
    centroid   geometry(Point, 4326) GENERATED ALWAYS AS (ST_PointOnSurface(geom)) STORED
);
CREATE INDEX IF NOT EXISTS comuni_geom_gix ON comuni USING GIST (geom);
CREATE INDEX IF NOT EXISTS comuni_aoi_idx  ON comuni (aoi_id);

CREATE TABLE IF NOT EXISTS cell_comune (
    cell_id    text PRIMARY KEY REFERENCES grid_cells (id) ON DELETE CASCADE,
    istat_code text NOT NULL REFERENCES comuni (istat_code) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS cell_comune_istat_idx ON cell_comune (istat_code);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_comune_risk AS
SELECT
    c.istat_code,
    c.name,
    c.aoi_id,
    COUNT(m.cell_id)                                            AS n_cells,
    COUNT(*) FILTER (WHERE m.risk_level = 'None')               AS n_none,
    COUNT(*) FILTER (WHERE m.risk_level = 'Low')                AS n_low,
    COUNT(*) FILTER (WHERE m.risk_level = 'Moderate')           AS n_moderate,
    COUNT(*) FILTER (WHERE m.risk_level = 'High')               AS n_high,
    COUNT(*) FILTER (WHERE m.risk_level = 'VeryHigh')           AS n_veryhigh,
    COUNT(*) FILTER (WHERE m.risk_level IN ('High','VeryHigh')) AS n_alert,
    MAX(m.risk_score)                                           AS max_score,
    COALESCE(
        (array_agg(m.risk_level ORDER BY m.risk_score DESC NULLS LAST))[1],
        'None'
    )                                                           AS worst_class,
    COALESCE(SUM((m.factors->>'e')::double precision)
             FILTER (WHERE m.risk_level IN ('High','VeryHigh')), 0) AS exposure_rank,
    c.geom,
    c.centroid
FROM comuni c
LEFT JOIN cell_comune cc ON cc.istat_code = c.istat_code
LEFT JOIN mv_latest_risk m ON m.cell_id = cc.cell_id AND m.risk_score IS NOT NULL
GROUP BY c.istat_code, c.name, c.aoi_id, c.geom, c.centroid
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS mv_comune_risk_pk   ON mv_comune_risk (istat_code);
CREATE INDEX IF NOT EXISTS mv_comune_risk_geom_gix    ON mv_comune_risk USING GIST (geom);
CREATE INDEX IF NOT EXISTS mv_comune_risk_aoi_idx     ON mv_comune_risk (aoi_id);

-- Comune refresh helper (mirrors refresh_mv_latest_risk semantics).
CREATE OR REPLACE FUNCTION refresh_mv_comune_risk() RETURNS integer
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_comune_risk;
        RETURN 1;
    EXCEPTION
        WHEN feature_not_supported THEN
            REFRESH MATERIALIZED VIEW mv_comune_risk;
            RETURN 0;
        WHEN OTHERS THEN
            RAISE NOTICE 'refresh_mv_comune_risk failed: %', SQLERRM;
            RETURN -1;
    END;
END $$;

-- Chain comune refresh onto the single supported latest-refresh path so every
-- existing caller (PersistResult) updates the comune rollup for free. Redefine
-- (never edit migration 007) — refresh latest first, then comune.
CREATE OR REPLACE FUNCTION refresh_mv_latest_risk() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE latest_rc integer;
BEGIN
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_risk;
        latest_rc := 1;
    EXCEPTION
        WHEN feature_not_supported THEN
            REFRESH MATERIALIZED VIEW mv_latest_risk;
            latest_rc := 0;
        WHEN OTHERS THEN
            RAISE NOTICE 'refresh_mv_latest_risk failed: %', SQLERRM;
            RETURN -1;
    END;
    -- Comune depends on the freshly refreshed latest view. Best-effort:
    -- a comune-refresh failure must not mask a successful latest refresh.
    PERFORM refresh_mv_comune_risk();
    RETURN latest_rc;
END $$;
```

- [ ] **Step 2: Write the integration test**

Create `tests/integration/test_comune_matview.py` (uses the testcontainer Postgres fixture — mirror an existing integration test's fixture import):

```python
"""mv_comune_risk rollup semantics against real PostGIS."""

from __future__ import annotations

import pytest

from limen.data.migrate import run_migrations

pytestmark = pytest.mark.integration


async def _seed_minimal(conn) -> None:
    await conn.execute(
        "INSERT INTO aoi (id, name, geom) VALUES "
        "('it-test','Test', ST_GeomFromText('POLYGON((0 0,0 2,2 2,2 0,0 0))',4326))"
    )
    # two cells, both inside one comune polygon
    for i, (x, cls, score, e) in enumerate(
        [(0.5, "High", 0.8, 0.9), (1.5, "Low", 0.2, 0.1)]
    ):
        cid = f"it-test|0|{i}"
        await conn.execute(
            "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) VALUES "
            "($1,'it-test',0,$2, ST_GeomFromText($3,4326), 1.0)",
            cid, i,
            f"POLYGON(({x} 0.4,{x} 0.6,{x+0.1} 0.6,{x+0.1} 0.4,{x} 0.4))",
        )
        await conn.execute(
            "INSERT INTO risk_assessments (cell_id, aoi_id, score, class, factors, "
            "explanation, computed_at, horizon, pipeline_version) VALUES "
            "($1,'it-test',$2,$3, jsonb_build_object('e',$4::float), '{}'::jsonb, now(), 'now','v1')",
            cid, score, cls, e,
        )
    await conn.execute(
        "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES "
        "('C001','Testville','it-test', "
        "ST_Multi(ST_GeomFromText('POLYGON((0 0,0 2,2 2,2 0,0 0))',4326)))"
    )
    await conn.execute(
        "INSERT INTO cell_comune (cell_id, istat_code) "
        "SELECT g.id, c.istat_code FROM grid_cells g JOIN comuni c "
        "ON ST_Contains(c.geom, g.centroid)"
    )


async def test_comune_rollup(pg_conn) -> None:  # pg_conn: existing integration fixture
    await run_migrations()
    await _seed_minimal(pg_conn)
    await pg_conn.execute("SELECT refresh_mv_latest_risk()")  # also refreshes comune
    row = await pg_conn.fetchrow("SELECT * FROM mv_comune_risk WHERE istat_code='C001'")
    assert row["worst_class"] == "High"       # worst cell drives the headline
    assert row["n_alert"] == 1                # one High+ cell
    assert row["n_cells"] == 2
    assert float(row["exposure_rank"]) == pytest.approx(0.9)  # E of the High cell only
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `make up-dev && uv run pytest tests/integration/test_comune_matview.py -v`
Expected: PASS (migration applies 026, rollup returns worst_class=High, n_alert=1, exposure_rank≈0.9).

- [ ] **Step 4: Quality gates**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: All checks passed.

- [ ] **Step 5: Commit**

```bash
git add src/limen/data/migrations/026_comuni.sql tests/integration/test_comune_matview.py
git commit -m "feat(db): comuni + cell_comune + mv_comune_risk (chained refresh)"
```

---

## Task 2: `limen seed-comuni` — import boundaries + tag cells

**Files:**
- Create: `src/limen/cli/seed_comuni.py`
- Modify: `src/limen/cli/main.py` (register subcommand)
- Test: `tests/unit/test_seed_comuni_sql.py`

**Note on the source column:** the GeoServer table is `com01012023_g`. The
municipal name column is `comune` (confirmed in `integrations/geoserver_source/comuni.py`).
The full ISTAT municipal code is the standard column `pro_com_t` (text). Step 1
verifies both before the run; adjust the SELECT if a deployment differs.

- [ ] **Step 1: Verify the GeoServer comuni columns (one-time, live)**

Run (against the GeoServer DSN):
`psql "$GEOSERVER_SOURCE__DB_DSN" -c "\d com01012023_g"`
Expected: columns include `comune` (name), `pro_com_t` (ISTAT code), `geom`.
If the code column differs (e.g. `pro_com`), use that name in Step 3's SELECT.

- [ ] **Step 2: Write the runner**

Create `src/limen/cli/seed_comuni.py`:

```python
"""``limen seed-comuni`` — import ISTAT comune boundaries into the operational
DB and tag every grid cell with its comune (static, idempotent).

Reads the boundaries once from the GeoServer PostGIS (GEOSERVER_SOURCE__DB_DSN);
nothing queries that DB in the hot path afterwards. Comuni whose centroid falls
outside every seeded AOI are skipped (keeps the table to seeded regions).
"""

from __future__ import annotations

import asyncpg

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.data.migrate import run_migrations

log = get_logger(__name__)

_SRC_SQL = """
SELECT pro_com_t::text AS istat_code, comune AS name,
       ST_AsBinary(ST_Multi(ST_Force2D(ST_Transform(geom, 4326)))) AS wkb
FROM com01012023_g
WHERE geom IS NOT NULL
"""


async def run() -> int:
    settings = get_settings()
    dsn = settings.geoserver_source.db_dsn
    if not dsn:
        log.error("cli.seed_comuni.no_dsn", need="GEOSERVER_SOURCE__DB_DSN")
        return 2

    src = await asyncpg.connect(dsn)
    try:
        rows = await src.fetch(_SRC_SQL)
    finally:
        await src.close()

    async with lifespan_pool():
        await run_migrations()
        inserted = 0
        async with acquire() as conn:
            async with conn.transaction():
                for r in rows:
                    # aoi_id via spatial containment against seeded AOIs; skip
                    # comuni outside every seeded region.
                    res = await conn.execute(
                        """
                        INSERT INTO comuni (istat_code, name, aoi_id, geom)
                        SELECT $1, $2, a.id, ST_SetSRID(ST_GeomFromWKB($3), 4326)
                        FROM aoi a
                        WHERE ST_Contains(
                            a.geom, ST_PointOnSurface(ST_SetSRID(ST_GeomFromWKB($3), 4326)))
                        LIMIT 1
                        ON CONFLICT (istat_code) DO UPDATE
                            SET name = EXCLUDED.name, aoi_id = EXCLUDED.aoi_id,
                                geom = EXCLUDED.geom
                        """,
                        r["istat_code"], r["name"], r["wkb"],
                    )
                    if res.endswith(("1",)):
                        inserted += 1
                # Tag cells (static): comune contains cell centroid.
                await conn.execute(
                    """
                    INSERT INTO cell_comune (cell_id, istat_code)
                    SELECT g.id, c.istat_code
                    FROM grid_cells g
                    JOIN comuni c ON ST_Contains(c.geom, g.centroid)
                    ON CONFLICT (cell_id) DO UPDATE SET istat_code = EXCLUDED.istat_code
                    """
                )
                tagged = await conn.fetchval("SELECT COUNT(*) FROM cell_comune")
        async with acquire() as conn:
            rc = await conn.fetchval("SELECT refresh_mv_latest_risk()")
    log.info("cli.seed_comuni.done", comuni=inserted, cells_tagged=tagged, refresh=rc)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 3: Register the subcommand**

Modify `src/limen/cli/main.py`:
- Add import near the other CLI imports:
  `from limen.cli.seed_comuni import run as _run_seed_comuni`
- Add a subparser after the `seed` parser:
  ```python
  sub.add_parser(
      "seed-comuni",
      help="import ISTAT comune boundaries + tag cells (needs GEOSERVER_SOURCE__DB_DSN)",
  )
  ```
- Add to the `runners` dict: `"seed-comuni": _run_seed_comuni,`

- [ ] **Step 4: Write a unit test for the tagging SQL shape (no external DB)**

Create `tests/unit/test_seed_comuni_sql.py`:

```python
"""seed-comuni: the SELECT against the GeoServer source is well-formed."""

from __future__ import annotations

from limen.cli.seed_comuni import _SRC_SQL


def test_src_sql_selects_expected_columns() -> None:
    s = _SRC_SQL.lower()
    assert "pro_com_t" in s and "comune" in s
    assert "st_asbinary" in s and "st_multi" in s
    assert "com01012023_g" in s
```

- [ ] **Step 5: Run the unit test + CLI wiring**

Run: `uv run pytest tests/unit/test_seed_comuni_sql.py -v && uv run limen --help | grep seed-comuni`
Expected: PASS; help lists `seed-comuni`.

- [ ] **Step 6: Live smoke (real DBs up)**

Run: `uv run limen seed-comuni`
Expected: log `cli.seed_comuni.done comuni=<N> cells_tagged=<M> refresh=1` with N>0, M>0.

- [ ] **Step 7: Commit**

```bash
git add src/limen/cli/seed_comuni.py src/limen/cli/main.py tests/unit/test_seed_comuni_sql.py
git commit -m "feat(cli): limen seed-comuni — import boundaries + tag cells"
```

---

## Task 3: Comune-risk repo + REST endpoints

**Files:**
- Create: `src/limen/data/repos/comune_risk.py`
- Create: `src/limen/api/endpoints/comuni.py`
- Modify: `src/limen/api/endpoints/__init__.py`
- Modify: `src/limen/api/schemas.py` (DTOs)
- Test: `tests/unit/test_comune_endpoints.py`

- [ ] **Step 1: Add DTOs**

Append to `src/limen/api/schemas.py`:

```python
class ComuneRisk(BaseModel):
    istat_code: str
    name: str
    aoi_id: str
    worst_class: str
    max_score: float
    n_cells: int
    n_alert: int
    counts: dict[str, int]
    exposure_rank: float


class ComuneListResponse(BaseModel):
    comuni: list[ComuneRisk]


class ComuneDetailResponse(BaseModel):
    comune: ComuneRisk
    cells: list[dict[str, object]]
```

(If `BaseModel` isn't already imported in schemas.py, add `from pydantic import BaseModel`.)

- [ ] **Step 2: Write the repo**

Create `src/limen/data/repos/comune_risk.py`:

```python
"""Read queries over mv_comune_risk (leaderboard + detail)."""

from __future__ import annotations

from typing import Any

from limen.data.db import acquire

_COLS = (
    "istat_code, name, aoi_id, worst_class, max_score, n_cells, n_alert, "
    "n_none, n_low, n_moderate, n_high, n_veryhigh, exposure_rank"
)


def _to_comune(row: Any) -> dict[str, Any]:
    return {
        "istat_code": row["istat_code"],
        "name": row["name"],
        "aoi_id": row["aoi_id"],
        "worst_class": row["worst_class"],
        "max_score": round(float(row["max_score"] or 0.0), 3),
        "n_cells": int(row["n_cells"]),
        "n_alert": int(row["n_alert"]),
        "counts": {
            "None": int(row["n_none"]), "Low": int(row["n_low"]),
            "Moderate": int(row["n_moderate"]), "High": int(row["n_high"]),
            "VeryHigh": int(row["n_veryhigh"]),
        },
        "exposure_rank": round(float(row["exposure_rank"] or 0.0), 3),
    }


async def top_comuni(*, aoi_id: str | None, limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    async with acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_COLS} FROM mv_comune_risk
            WHERE n_alert > 0 AND ($1::text IS NULL OR aoi_id = $1)
            ORDER BY exposure_rank DESC, n_alert DESC, max_score DESC
            LIMIT $2
            """,
            aoi_id, limit,
        )
    return [_to_comune(r) for r in rows]


async def comune_detail(istat_code: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_COLS} FROM mv_comune_risk WHERE istat_code = $1", istat_code
        )
        if row is None:
            return None
        cells = await conn.fetch(
            """
            SELECT m.cell_id, m.risk_score AS score, m.risk_level AS level
            FROM cell_comune cc
            JOIN mv_latest_risk m ON m.cell_id = cc.cell_id
            WHERE cc.istat_code = $1 AND m.risk_score IS NOT NULL
            ORDER BY m.risk_score DESC
            LIMIT 500
            """,
            istat_code,
        )
    return {
        "comune": _to_comune(row),
        "cells": [
            {"cell_id": c["cell_id"], "score": round(float(c["score"]), 3),
             "level": c["level"]}
            for c in cells
        ],
    }
```

- [ ] **Step 3: Write the endpoints**

Create `src/limen/api/endpoints/comuni.py`:

```python
"""Comune risk lookup — leaderboard + detail (read-only over mv_comune_risk)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from limen.api.schemas import ComuneDetailResponse, ComuneListResponse, ComuneRisk
from limen.data.repos import comune_risk

router = APIRouter(tags=["comuni"])


@router.get("/api/comuni", response_model=ComuneListResponse)
async def list_comuni(aoi: str | None = None, limit: int = 50) -> ComuneListResponse:
    rows = await comune_risk.top_comuni(aoi_id=aoi, limit=limit)
    return ComuneListResponse(comuni=[ComuneRisk(**r) for r in rows])


@router.get("/api/comune/{istat_code}", response_model=ComuneDetailResponse)
async def get_comune(istat_code: str) -> ComuneDetailResponse:
    detail = await comune_risk.comune_detail(istat_code)
    if detail is None:
        raise HTTPException(status_code=404, detail="comune non trovato")
    return ComuneDetailResponse(comune=ComuneRisk(**detail["comune"]), cells=detail["cells"])
```

- [ ] **Step 4: Register the router**

Modify `src/limen/api/endpoints/__init__.py`: add `comuni` to the import line and append `comuni.router` to the `all_routers()` tuple.

- [ ] **Step 5: Write endpoint tests (no DB — stub the repo)**

Create `tests/unit/test_comune_endpoints.py`:

```python
"""Comune REST endpoints — dispatch + 404 (repo stubbed, no DB)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api.endpoints import comuni as comuni_ep

_ROW = {
    "istat_code": "C001", "name": "Testville", "aoi_id": "it-test",
    "worst_class": "High", "max_score": 0.8, "n_cells": 2, "n_alert": 1,
    "counts": {"None": 0, "Low": 1, "Moderate": 0, "High": 1, "VeryHigh": 0},
    "exposure_rank": 0.9,
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _top(**kwargs: Any) -> list[dict[str, Any]]:
        return [_ROW]

    async def _detail(istat_code: str) -> dict[str, Any] | None:
        return {"comune": _ROW, "cells": []} if istat_code == "C001" else None

    monkeypatch.setattr(comuni_ep.comune_risk, "top_comuni", _top)
    monkeypatch.setattr(comuni_ep.comune_risk, "comune_detail", _detail)
    app = FastAPI()
    app.include_router(comuni_ep.router)
    return TestClient(app)


def test_list_comuni(client: TestClient) -> None:
    body = client.get("/api/comuni?aoi=it-test&limit=10").json()
    assert body["comuni"][0]["worst_class"] == "High"
    assert body["comuni"][0]["counts"]["High"] == 1


def test_comune_detail_and_404(client: TestClient) -> None:
    assert client.get("/api/comune/C001").json()["comune"]["name"] == "Testville"
    assert client.get("/api/comune/NOPE").status_code == 404
```

- [ ] **Step 6: Run tests + gates**

Run: `uv run pytest tests/unit/test_comune_endpoints.py -v && uv run mypy && uv run ruff check src tests`
Expected: PASS, mypy clean, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add src/limen/data/repos/comune_risk.py src/limen/api/endpoints/comuni.py \
  src/limen/api/endpoints/__init__.py src/limen/api/schemas.py tests/unit/test_comune_endpoints.py
git commit -m "feat(api): /api/comuni leaderboard + /api/comune/{id} detail"
```

---

## Task 4: MCP tools + A2A skills for comune

**Files:**
- Modify: `src/limen/mcp/tools.py`, `src/limen/mcp/server.py`
- Modify: `src/limen/a2a/skills.py`
- Test: `tests/unit/test_comune_agent_tools.py`

- [ ] **Step 1: Add MCP tool bodies**

Append to `src/limen/mcp/tools.py`:

```python
async def comune_risk(istat_code: str) -> dict[str, Any]:
    """Comune rollup (worst class, counts, exposure) for one ISTAT code."""
    from limen.data.repos.comune_risk import comune_detail

    detail = await comune_detail(istat_code)
    return detail["comune"] if detail else {"error": f"comune {istat_code!r} not found"}


async def top_comuni(limit: int = 10, aoi_id: str | None = None) -> list[dict[str, Any]]:
    """Comuni with alerting cells, ranked by exposure (national or per-AOI)."""
    from limen.data.repos.comune_risk import top_comuni as _top

    return await _top(aoi_id=aoi_id, limit=limit)
```

- [ ] **Step 2: Register in the MCP server**

Modify `src/limen/mcp/server.py`: import `comune_risk, top_comuni`, add two tools mirroring `tool_risk_summary`:

```python
    @mcp.tool()
    async def tool_comune_risk(istat_code: str) -> dict[str, Any]:
        """Comune rollup (worst class, class counts, exposure)."""
        return await comune_risk(istat_code)

    @mcp.tool()
    async def tool_top_comuni(limit: int = 10, aoi_id: str | None = None) -> list[dict[str, Any]]:
        """Comuni with alerting cells, exposure-ranked."""
        return await top_comuni(limit=limit, aoi_id=aoi_id)
```

Also add both to `SERVER_INSTRUCTIONS` read-tools list.

- [ ] **Step 3: Add A2A skills**

Modify `src/limen/a2a/skills.py`: add handlers + `Skill` entries:

```python
async def _comune_risk(p: dict[str, Any]) -> Any:
    code = p.get("istat_code")
    if not isinstance(code, str) or not code:
        raise ValueError("comune_risk requires an 'istat_code' string param")
    return await tools.comune_risk(code)


async def _top_comuni(p: dict[str, Any]) -> Any:
    return await tools.top_comuni(limit=int(p.get("limit", 10)), aoi_id=p.get("aoi_id"))
```

Add to the `SKILLS` dict:

```python
        Skill(
            id="top_comuni",
            name="Comuni a rischio",
            description="Comuni con celle in allerta, ordinati per esposizione. "
            "Parametri: 'limit', 'aoi_id'.",
            handler=_top_comuni,
            tags=("landslide", "flood", "comune", "ranking"),
            examples=("I comuni più a rischio in Puglia",),
        ),
        Skill(
            id="comune_risk",
            name="Rischio di un comune",
            description="Rollup di un comune (classe peggiore, conteggi, esposizione). "
            "Richiede 'istat_code'.",
            handler=_comune_risk,
            tags=("landslide", "flood", "comune"),
            examples=("Che rischio c'è nel comune C001?",),
        ),
```

- [ ] **Step 4: Write tests**

Create `tests/unit/test_comune_agent_tools.py`:

```python
"""Comune MCP tool bodies + A2A skill routing (repo stubbed, no DB)."""

from __future__ import annotations

from typing import Any

import pytest

from limen.a2a.models import DataPart, Message
from limen.a2a.skills import SKILLS, resolve_invocation
from limen.mcp import tools


@pytest.fixture(autouse=True)
def _stub(monkeypatch: pytest.MonkeyPatch) -> None:
    import limen.data.repos.comune_risk as cr

    async def _detail(code: str) -> dict[str, Any] | None:
        return {"comune": {"istat_code": code, "worst_class": "High"}, "cells": []}

    async def _top(*, aoi_id: str | None, limit: int) -> list[dict[str, Any]]:
        return [{"istat_code": "C001", "worst_class": "High"}]

    monkeypatch.setattr(cr, "comune_detail", _detail)
    monkeypatch.setattr(cr, "top_comuni", _top)


async def test_comune_risk_tool() -> None:
    assert (await tools.comune_risk("C001"))["worst_class"] == "High"


async def test_a2a_comune_skills_registered() -> None:
    assert "top_comuni" in SKILLS and "comune_risk" in SKILLS
    msg = Message(role="user", message_id="m1",
                  parts=[DataPart(data={"skill": "comune_risk", "params": {"istat_code": "C001"}})])
    skill_id, params = resolve_invocation(msg)
    assert skill_id == "comune_risk"
    assert (await SKILLS[skill_id].handler(params))["worst_class"] == "High"
```

- [ ] **Step 5: Run tests + gates**

Run: `uv run pytest tests/unit/test_comune_agent_tools.py -v && uv run mypy && uv run ruff check src tests`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add src/limen/mcp/tools.py src/limen/mcp/server.py src/limen/a2a/skills.py \
  tests/unit/test_comune_agent_tools.py
git commit -m "feat(agents): comune_risk + top_comuni MCP tools & A2A skills"
```

---

## Task 5: Report — "comuni a maggior rischio" section

**Files:**
- Modify: `src/limen/report/render.py` (add field to `ReportView`)
- Modify: `src/limen/report/builder.py` (query + populate)
- Modify: `src/limen/report/templates/report.html.j2` (render)
- Test: `tests/unit/test_report_comuni.py`

- [ ] **Step 1: Add the view field**

Modify `src/limen/report/render.py`: add to `ReportView` a field
`top_comuni: list[dict[str, object]] = field(default_factory=list)`.

- [ ] **Step 2: Populate in the builder**

In `src/limen/report/builder.py`, where the `ReportView` is assembled, add a
query and pass it through. Reuse the repo:

```python
from limen.data.repos.comune_risk import top_comuni as _top_comuni_repo
# ... inside build_report, after clusters are computed:
view.top_comuni = await _top_comuni_repo(aoi_id=None, limit=15)
```

(If `ReportView` is constructed all-at-once rather than mutated, pass
`top_comuni=await _top_comuni_repo(aoi_id=None, limit=15)` into the constructor.)

- [ ] **Step 3: Render in the template**

Add to `src/limen/report/templates/report.html.j2`, after the clusters loop:

```html
  {% if view.top_comuni %}
  <section class="national">
    <h2>Comuni a maggior rischio</h2>
    <table class="int-table">
      <thead><tr><th>Comune</th><th>Classe</th><th>Celle in allerta</th></tr></thead>
      <tbody>
        {% for c in view.top_comuni %}
        <tr><td>{{ c.name }}</td><td>{{ c.worst_class }}</td><td>{{ c.n_alert }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
  {% endif %}
```

- [ ] **Step 4: Write a render test**

Create `tests/unit/test_report_comuni.py`:

```python
"""Report renders the comuni section when data is present."""

from __future__ import annotations

from limen.report.render import ReportView, render_html


def test_comuni_section_rendered() -> None:
    view = ReportView(
        title="t", valuation_time="2026-07-21", pipeline_version="v1",
        national_summary="", basemap_url="", basemap_attribution="",
        top_comuni=[{"name": "Testville", "worst_class": "High", "n_alert": 3}],
    )
    html = render_html(view)
    assert "Comuni a maggior rischio" in html
    assert "Testville" in html
    assert ">3<" in html or "3" in html
```

- [ ] **Step 5: Run test + gates**

Run: `uv run pytest tests/unit/test_report_comuni.py -v && uv run ruff check src tests`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add src/limen/report/render.py src/limen/report/builder.py \
  src/limen/report/templates/report.html.j2 tests/unit/test_report_comuni.py
git commit -m "feat(report): comuni a maggior rischio section"
```

---

## Task 6: Alert enrichment — comune in the payload

**Files:**
- Modify: `src/limen/notifications/base.py` (add `comune` to `AlertedCell`)
- Modify: `src/limen/agents/executors/alert_dispatch.py` (populate it)
- Test: `tests/unit/test_alert_comune.py`

- [ ] **Step 1: Add the field**

Modify `src/limen/notifications/base.py`: add to `AlertedCell`
`comune: str | None = None`. (Optional field ⇒ existing payload construction
keeps working; no other change to `_format_summary_it`.)

- [ ] **Step 2: Populate it in the dispatch executor**

In `src/limen/agents/executors/alert_dispatch.py`, where `AlertedCell`s are
built, batch-look-up the comune name from `cell_comune` + `comuni` and set it.
Add a helper and call it before constructing the payload:

```python
from limen.data.db import acquire

async def _comuni_for_cells(cell_ids: list[str]) -> dict[str, str]:
    if not cell_ids:
        return {}
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cc.cell_id, c.name
            FROM cell_comune cc JOIN comuni c ON c.istat_code = cc.istat_code
            WHERE cc.cell_id = ANY($1::text[])
            """,
            cell_ids,
        )
    return {r["cell_id"]: r["name"] for r in rows}
```

Then when building each `AlertedCell`, pass `comune=comuni_map.get(record.cell_id)`.
(Look up `comuni_map = await _comuni_for_cells([r.cell_id for r, _ in take])` once.)

- [ ] **Step 3: Write the test**

Create `tests/unit/test_alert_comune.py`:

```python
"""AlertedCell carries an optional comune (payload enrichment)."""

from __future__ import annotations

from limen.core.models.risk import RiskLevel
from limen.notifications.base import AlertedCell


def test_alerted_cell_optional_comune() -> None:
    a = AlertedCell(cell_id="c1", score=0.8, level=RiskLevel.High, priority=1.0)
    assert a.comune is None
    b = AlertedCell(cell_id="c1", score=0.8, level=RiskLevel.High, priority=1.0, comune="Testville")
    assert b.comune == "Testville"
```

- [ ] **Step 4: Run test + gates**

Run: `uv run pytest tests/unit/test_alert_comune.py -v && uv run mypy && uv run ruff check src tests`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/limen/notifications/base.py src/limen/agents/executors/alert_dispatch.py \
  tests/unit/test_alert_comune.py
git commit -m "feat(alerts): enrich alerted cells with comune name"
```

---

## Task 7: Frontend — comune map layer (choropleth + High+ badges + drill-down)

**Files:**
- Modify: `frontend/src/components/RiskMap.tsx`
- Test: `frontend/src/__tests__/RiskMap.test.tsx` (extend)

- [ ] **Step 1: Add the comune source + layers**

In `RiskMap.tsx`, alongside the existing `public.v_region_tiles` source, add a
`public.mv_comune_risk` vector source and two layers (fill + High+ badge). The
fill colour reuses the shared `riskColor` mapping on `worst_class`; the badge
symbol layer filters to High/VeryHigh and labels `n_alert`.

```typescript
// source
sources["comuni"] = {
  type: "vector",
  tiles: [`${tileserv}/public.mv_comune_risk/{z}/{x}/{y}.pbf`],
  minzoom: 6,
  maxzoom: 12,
};
// fill layer (choropleth by worst_class), visible zoom 7–11
{
  id: "comuni-fill",
  type: "fill",
  source: "comuni",
  "source-layer": "public.mv_comune_risk",
  minzoom: 7,
  maxzoom: 11,
  paint: {
    "fill-color": [
      "match", ["get", "worst_class"],
      "VeryHigh", "#bd0026", "High", "#f03b20", "Moderate", "#fd8d3c",
      "Low", "#fed976", /* None */ "#ffffb2",
    ],
    "fill-opacity": 0.55,
    "fill-outline-color": "#ffffff",
  },
}
// badge: count of alerting cells, only High+
{
  id: "comuni-badge",
  type: "symbol",
  source: "comuni",
  "source-layer": "public.mv_comune_risk",
  minzoom: 7,
  maxzoom: 11,
  filter: ["in", ["get", "worst_class"], ["literal", ["High", "VeryHigh"]]],
  layout: { "text-field": ["to-string", ["get", "n_alert"]], "text-size": 12 },
  paint: { "text-color": "#ffffff", "text-halo-color": "#1a2733", "text-halo-width": 1.5 },
}
```

- [ ] **Step 2: Wire the drill-down click**

Add a click handler on `comuni-fill` that flies to the comune and triggers the
existing cell-selection flow (reuse the `onCellClick`/fly-to already used for
cells — fit to the clicked feature bounds):

```typescript
map.on("click", "comuni-fill", (e) => {
  const f = e.features?.[0];
  if (!f) return;
  map.flyTo({ center: e.lngLat, zoom: Math.max(map.getZoom(), 11) });
});
```

- [ ] **Step 3: Extend the map test**

In `frontend/src/__tests__/RiskMap.test.tsx`, assert the comune source URL is
registered (mirror how the existing test checks the region/cell tile URLs). If
the test uses a maplibre mock, assert `addLayer` was called with `comuni-fill`.

```typescript
expect(addedLayerIds).toContain("comuni-fill");
expect(addedLayerIds).toContain("comuni-badge");
```

- [ ] **Step 4: Run lint + test + build**

Run: `cd frontend && npm run lint && npm test && npm run build`
Expected: lint clean, tests pass, build OK.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RiskMap.tsx frontend/src/__tests__/RiskMap.test.tsx
git commit -m "feat(map): comune choropleth + High+ badges + drill-down"
```

---

## Task 8: Frontend — comune leaderboard + sidebar headline

**Files:**
- Create: `frontend/src/components/ComuneLeaderboard.tsx`
- Modify: `frontend/src/lib/api-client.ts`, `frontend/src/types.ts`
- Modify: `frontend/src/components/RegionAccordion.tsx` (headline in comune summary)
- Modify: `frontend/src/App.tsx` (mount leaderboard in the sidebar)
- Test: `frontend/src/__tests__/ComuneLeaderboard.test.tsx`

- [ ] **Step 1: Add types + api-client method**

In `frontend/src/types.ts`:

```typescript
export interface ComuneRisk {
  istat_code: string;
  name: string;
  aoi_id: string;
  worst_class: RiskLevel;
  max_score: number;
  n_cells: number;
  n_alert: number;
  counts: Record<RiskLevel, number>;
  exposure_rank: number;
}
export interface ComuneListResponse { comuni: ComuneRisk[]; }
```

In `frontend/src/lib/api-client.ts` add (and import `ComuneListResponse`):

```typescript
  getTopComuni(aoi?: string, limit = 50, signal?: AbortSignal): Promise<ComuneListResponse> {
    const qs = new URLSearchParams();
    if (aoi) qs.set("aoi", aoi);
    qs.set("limit", String(limit));
    return this.request<ComuneListResponse>(`/api/comuni?${qs.toString()}`, {}, signal);
  }
```

- [ ] **Step 2: Write the leaderboard component**

Create `frontend/src/components/ComuneLeaderboard.tsx`:

```tsx
import { useEffect, useState } from "react";

import { defaultApiClient } from "../lib/api-client";
import { riskColor } from "../lib/risk-colors";
import type { ComuneRisk } from "../types";

export default function ComuneLeaderboard(): JSX.Element {
  const [comuni, setComuni] = useState<ComuneRisk[]>([]);
  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getTopComuni(undefined, 20, ctrl.signal)
      .then((r) => setComuni(r.comuni))
      .catch(() => setComuni([]));
    return () => ctrl.abort();
  }, []);

  if (comuni.length === 0) return <></>;
  return (
    <section className="comuni-board" aria-label="Comuni a maggior rischio">
      <h3>Comuni a maggior rischio</h3>
      <ol>
        {comuni.map((c) => (
          <li key={c.istat_code}>
            <span className="dot" style={{ background: riskColor(c.worst_class) }} />
            <span className="cb-name">{c.name}</span>
            <span className="cb-meta">{c.n_alert} in allerta</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
```

(Confirm `riskColor` is exported from `frontend/src/lib/risk-colors.ts`; if the
export name differs, use that.)

- [ ] **Step 3: Mount it + sidebar headline**

- In `frontend/src/App.tsx`, add `<ComuneLeaderboard />` to the `dashboard`
  sidebar (after `<RegionAccordion .../>`).
- In `frontend/src/components/RegionAccordion.tsx`, the comune `<summary>` (from
  Fase 1) already shows min/max; add the worst-class label next to the name
  using the group's max level.

- [ ] **Step 4: Write the leaderboard test**

Create `frontend/src/__tests__/ComuneLeaderboard.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { getTopComuni } = vi.hoisted(() => ({ getTopComuni: vi.fn() }));
vi.mock("../lib/api-client", () => ({ defaultApiClient: { getTopComuni } }));

import ComuneLeaderboard from "../components/ComuneLeaderboard";

describe("ComuneLeaderboard", () => {
  it("renders comuni ranked with alert counts", async () => {
    getTopComuni.mockResolvedValue({
      comuni: [
        { istat_code: "C1", name: "Testville", aoi_id: "it-test", worst_class: "High",
          max_score: 0.8, n_cells: 2, n_alert: 3, counts: {}, exposure_rank: 0.9 },
      ],
    });
    render(<ComuneLeaderboard />);
    await waitFor(() => expect(screen.getByText("Testville")).toBeInTheDocument());
    expect(screen.getByText(/3 in allerta/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run lint + test + build**

Run: `cd frontend && npm run lint && npm test && npm run build`
Expected: lint clean, tests pass, build OK.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ComuneLeaderboard.tsx frontend/src/lib/api-client.ts \
  frontend/src/types.ts frontend/src/components/RegionAccordion.tsx frontend/src/App.tsx \
  frontend/src/__tests__/ComuneLeaderboard.test.tsx
git commit -m "feat(ui): comune leaderboard + worst-class headline in sidebar"
```

---

## Task 9: Docs + full validation

**Files:**
- Modify: `README.md`, `.env.example` (note `limen seed-comuni` + `GEOSERVER_SOURCE__DB_DSN`)

- [ ] **Step 1: Document**

Add a README bullet under the feature list describing the comune rollup (map
tier, leaderboard, `/api/comuni`, MCP/A2A, report). Note in `.env.example` that
`limen seed-comuni` needs `GEOSERVER_SOURCE__DB_DSN` and is a one-shot.

- [ ] **Step 2: Full gates + live end-to-end**

Run:
```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy
uv run pytest tests/unit -q
( cd frontend && npm run lint && npm test && npm run build )
# live (DBs up):
uv run limen seed-comuni
uv run limen monitor-once   # populates risk → refresh chains comune
curl -s localhost:8080/api/comuni?limit=5
```
Expected: all gates green; `/api/comuni` returns exposure-ranked comuni.

- [ ] **Step 3: Commit**

```bash
git add README.md .env.example
git commit -m "docs: comune risk aggregation (seed-comuni, /api/comuni)"
```

---

## Notes & invariants

- **Never edit migration 007**; the refresh chaining is a `CREATE OR REPLACE` in 026.
- `mv_comune_risk` mirrors `v_region_tiles` semantics (reads `mv_latest_risk` as-is). If forecast rows ever pollute `mv_latest_risk`, that is a pre-existing region-tiles concern, out of scope here.
- Endpoints hold no business logic — they call the repo. Aggregation is pure/deterministic; no LLM, no cloud.
- Thresholds stay in `regional_thresholds.yaml`; the only cutoff used (badge = High+) reuses the per-cell class, no new constant.
