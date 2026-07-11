# Report HTML statico delle zone a rischio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generare automaticamente (al boot + ogni ora) un report HTML statico e autosufficiente che mostra le zone a maggior rischio frana (cluster di celle contigue) con snapshot mappa e motivo dettagliato, conservando ogni versione in un archivio immutabile per il fact-checking futuro.

**Architecture:** Nuovo package `src/limen/report/` invocato da un job APScheduler (`limen-html-report`) e da un comando CLI (`limen report build`). Legge lo storico già persistito (`risk_assessments` append-only, `mv_latest_risk`), clusterizza le celle `High+` con PostGIS `ST_ClusterDBSCAN`, renderizza uno snapshot PNG per cluster (basemap raster + celle colorate), compila l'HTML con Jinja2 e scrive un output versionato immutabile con `manifest.json`. Nessuna duplicazione delle previsioni (già in DB), nessun richiamo LLM a build-time (riusa `briefing_it` persistito).

**Tech Stack:** Python 3.12, asyncpg + PostGIS, Jinja2 (già presente), Pillow (nuovo, optional group `report`), httpx via `limen.integrations._http`, APScheduler 4.

**Spec di riferimento:** `docs/superpowers/specs/2026-07-11-static-html-risk-report-design.md`

---

## File Structure

| File | Responsabilità |
|---|---|
| `pyproject.toml` | +optional group `report` (jinja2, pillow) |
| `src/limen/config/settings.py` | nuovi campi in `ReportSettings` |
| `src/limen/report/__init__.py` | export `build_report` |
| `src/limen/report/palette.py` | mirror di `RISK_CLASSES` (hex, label IT, range) — pure |
| `src/limen/report/reasons.py` | motivo deterministico da factors — pure (port di `CellPopup`) |
| `src/limen/report/clustering.py` | query `ST_ClusterDBSCAN` + raggruppamento in `Cluster` |
| `src/limen/report/geo.py` | matematica slippy-map (lon/lat→tile→pixel) — pure |
| `src/limen/report/snapshot.py` | bbox cluster → basemap raster + overlay celle → PNG (+ fallback SVG) |
| `src/limen/report/render.py` | Jinja2 → HTML |
| `src/limen/report/templates/report.html.j2` | template con CSS inline |
| `src/limen/report/archive.py` | output versionato immutabile + manifest + retention |
| `src/limen/report/builder.py` | orchestratore (idempotenza + wiring) |
| `src/limen/api/jobs/html_report.py` | `run_html_report(deps)` |
| `src/limen/api/jobs/registration.py` | registra `limen-html-report` |
| `src/limen/api/main.py` | kickoff fire-and-forget al boot |
| `src/limen/cli/report.py` | subcommand `limen report build` |
| `src/limen/cli/main.py` | dispatch del subcommand |

---

## Task 1: Dipendenze + settings

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/limen/config/settings.py:543-550` (`ReportSettings`)
- Test: `tests/unit/test_report_settings.py`

- [ ] **Step 1: Aggiungere l'optional group `report` in `pyproject.toml`**

Dopo il blocco `dependencies = [...]` (dopo riga 44), aggiungere o estendere `[dependency-groups]`. Se il gruppo esiste già, aggiungere solo la voce; altrimenti creare:

```toml
[dependency-groups]
report = [
    "jinja2>=3.1",
    "pillow>=10.4",
]
```

- [ ] **Step 2: Estendere `ReportSettings` con i campi del report HTML**

In `src/limen/config/settings.py`, dentro `class ReportSettings` (dopo `hour_utc`, riga 550), aggiungere. `Path` e `RiskLevel` vanno importati in testa al file se non presenti (`from pathlib import Path`, `from limen.core.models.risk import RiskLevel`):

```python
    # --- Report HTML statico (job limen-html-report) ---
    html_enabled: bool = True
    html_interval_hours: int = Field(default=1, ge=1)
    html_run_at_startup: bool = True
    html_output_dir: Path = Path("report")
    html_max_clusters: int = Field(default=50, ge=1)
    html_min_level: RiskLevel = RiskLevel.High
    html_cluster_eps_deg: float = Field(default=0.02, gt=0)
    html_archive_keep: int = Field(default=240, ge=1)
    html_basemap_url_template: str = (
        "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
    )
    html_basemap_attribution: str = "© OpenStreetMap contributors © CARTO"
    html_publish: bool = False
```

- [ ] **Step 3: Scrivere il test dei default**

```python
# tests/unit/test_report_settings.py
from limen.config.settings import ReportSettings


def test_report_html_defaults() -> None:
    s = ReportSettings()
    assert s.html_enabled is True
    assert s.html_interval_hours == 1
    assert s.html_run_at_startup is True
    assert s.html_max_clusters == 50
    assert s.html_min_level.value == "High"
    assert s.html_publish is False


def test_report_html_env_override(monkeypatch) -> None:
    monkeypatch.setenv("REPORT__HTML_INTERVAL_HOURS", "6")
    monkeypatch.setenv("REPORT__HTML_ENABLED", "false")
    from limen.config.settings import Settings

    s = Settings().report
    assert s.html_interval_hours == 6
    assert s.html_enabled is False
```

- [ ] **Step 4: Installare e testare**

Run: `uv sync --all-groups && uv run pytest tests/unit/test_report_settings.py -v`
Expected: PASS (2 test). `python -c "import PIL, jinja2"` non deve fallire.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/limen/config/settings.py tests/unit/test_report_settings.py
git commit -m "feat(report): settings + optional deps for static HTML report"
```

---

## Task 2: Palette (mirror di RISK_CLASSES)

**Files:**
- Create: `src/limen/report/__init__.py`
- Create: `src/limen/report/palette.py`
- Test: `tests/unit/test_report_palette.py`

- [ ] **Step 1: Scrivere il test**

```python
# tests/unit/test_report_palette.py
from limen.core.models.risk import RiskLevel
from limen.report.palette import RISK_CLASSES, color_for, label_for


def test_five_classes_cover_unit_interval() -> None:
    assert len(RISK_CLASSES) == 5
    assert RISK_CLASSES[0].range[0] == 0.0
    assert RISK_CLASSES[-1].range[1] == 1.0
    # contiguo, senza buchi
    for a, b in zip(RISK_CLASSES, RISK_CLASSES[1:]):
        assert a.range[1] == b.range[0]


def test_color_and_label_by_level() -> None:
    assert color_for(RiskLevel.VeryHigh) == "#bd0026"
    assert color_for(RiskLevel.None_) == "#ffffb2"
    assert label_for(RiskLevel.High) == "Alto"
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_report_palette.py -v`
Expected: FAIL con `ModuleNotFoundError: limen.report`.

- [ ] **Step 3: Creare il package e la palette**

```python
# src/limen/report/__init__.py
"""Generatore del report HTML statico delle zone a rischio."""
```

```python
# src/limen/report/palette.py
"""Palette rischio server-side — mirror di frontend/src/lib/risk-colors.ts.

Duplicata di proposito: il report gira server-side e non può importare il TS.
ColorBrewer YlOrRd, 5 classi, mai solo-colore (label + range accanto al colore).
"""

from __future__ import annotations

from dataclasses import dataclass

from limen.core.models.risk import RiskLevel


@dataclass(frozen=True)
class RiskClass:
    level: RiskLevel
    label_it: str
    color: str
    range: tuple[float, float]


RISK_CLASSES: list[RiskClass] = [
    RiskClass(RiskLevel.None_, "Nullo", "#ffffb2", (0.0, 0.15)),
    RiskClass(RiskLevel.Low, "Basso", "#fecc5c", (0.15, 0.35)),
    RiskClass(RiskLevel.Moderate, "Moderato", "#fd8d3c", (0.35, 0.55)),
    RiskClass(RiskLevel.High, "Alto", "#f03b20", (0.55, 0.75)),
    RiskClass(RiskLevel.VeryHigh, "Molto alto", "#bd0026", (0.75, 1.0)),
]

_BY_LEVEL = {c.level: c for c in RISK_CLASSES}


def color_for(level: RiskLevel) -> str:
    return _BY_LEVEL[level].color


def label_for(level: RiskLevel) -> str:
    return _BY_LEVEL[level].label_it
```

- [ ] **Step 4: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_report_palette.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add src/limen/report/__init__.py src/limen/report/palette.py tests/unit/test_report_palette.py
git commit -m "feat(report): server-side risk palette mirror"
```

---

## Task 3: Motivo deterministico (port di CellPopup)

**Files:**
- Create: `src/limen/report/reasons.py`
- Test: `tests/unit/test_report_reasons.py`

Porta la logica `plainSummary`/`verdict` di `frontend/src/components/CellPopup.tsx` (righe 49-119) in Python. Input = i cinque scalari componenti `s,m,e,f,h` (0-1) + il livello.

- [ ] **Step 1: Scrivere il test**

```python
# tests/unit/test_report_reasons.py
from limen.core.models.risk import RiskLevel
from limen.report.reasons import plain_summary, verdict


def test_dominant_driver_is_rain_when_meteo_highest() -> None:
    text = plain_summary(s=0.1, m=0.8, e=0.0, f=0.0, h=0.0)
    assert "pioggia" in text.lower()
    assert "verso l'alto" in text


def test_no_rain_notes_historical_fragility() -> None:
    text = plain_summary(s=0.6, m=0.0, e=0.0, f=0.0, h=0.0)
    assert "versante" in text.lower()
    assert "Non c'è pioggia" in text


def test_verdict_high_is_warn() -> None:
    v = verdict(RiskLevel.High)
    assert v.tone == "warn"
    assert "attenzionare" in v.text.lower()
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_report_reasons.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementare `reasons.py`**

```python
# src/limen/report/reasons.py
"""Motivo del rischio in linguaggio piano — deterministico, dal breakdown.

Port di plainSummary/verdict in frontend/src/components/CellPopup.tsx.
Niente LLM, niente numeri inventati: solo i contributi componenti S/M/E/F/H.
"""

from __future__ import annotations

from dataclasses import dataclass

from limen.core.models.risk import RiskLevel

_DRIVERS: list[tuple[str, str]] = [
    ("s", "dalla natura del versante: geologia, pendenza e frane del passato"),
    ("m", "dalla spinta della pioggia recente"),
    ("e", "dalle scosse sismiche recenti"),
    ("f", "dall'effetto di incendi recenti"),
    ("h", "dalla pericolosità idraulica della zona"),
]


@dataclass(frozen=True)
class Verdict:
    text: str
    tone: str  # "ok" | "watch" | "warn"


def verdict(level: RiskLevel) -> Verdict:
    if level in (RiskLevel.VeryHigh, RiskLevel.High):
        return Verdict("Da attenzionare: rischio alto sul versante.", "warn")
    if level is RiskLevel.Moderate:
        return Verdict(
            "Da tenere sotto osservazione: rischio moderato.", "watch"
        )
    return Verdict("Nessuna preoccupazione immediata: rischio basso.", "ok")


def plain_summary(*, s: float, m: float, e: float, f: float, h: float) -> str:
    scalars = {"s": s, "m": m, "e": e, "f": f, "h": h}
    parts: list[str] = []
    top_key, top_phrase = max(_DRIVERS, key=lambda d: scalars[d[0]])
    if scalars[top_key] > 0.05:
        parts.append(f"Il punteggio nasce soprattutto {top_phrase}.")
    if m < 0.05:
        parts.append(
            "Non c'è pioggia in corso: il punteggio riflette la fragilità "
            "storica del versante, non un pericolo in atto."
        )
    elif m < 0.2:
        parts.append("La pioggia recente incide poco.")
    elif m < 0.5:
        parts.append("La pioggia recente contribuisce in modo moderato.")
    else:
        parts.append("La pioggia recente sta spingendo il rischio verso l'alto.")
    return " ".join(parts)
```

- [ ] **Step 4: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_report_reasons.py -v`
Expected: PASS (3 test).

- [ ] **Step 5: Commit**

```bash
git add src/limen/report/reasons.py tests/unit/test_report_reasons.py
git commit -m "feat(report): deterministic plain-language reason (port of CellPopup)"
```

---

## Task 4: Clustering (query PostGIS + raggruppamento)

**Files:**
- Create: `src/limen/report/clustering.py`
- Test: `tests/unit/test_report_clustering.py`

La query (`ST_ClusterDBSCAN`) è integrazione; il raggruppamento delle righe in `Cluster` è pura e testabile in unità. Separa le due.

- [ ] **Step 1: Scrivere il test del raggruppamento puro**

```python
# tests/unit/test_report_clustering.py
from limen.report.clustering import ClusterRow, group_into_clusters


def _row(cid: str, cluster: int, score: float, level: str) -> ClusterRow:
    return ClusterRow(
        cluster_id=cluster,
        cell_id=cid,
        aoi_id="puglia",
        score=score,
        level=level,
        s=0.5, m=0.1, e=0.0, f=0.0, h=0.0,
        lon=16.0, lat=41.0,
        geom_json='{"type":"Polygon","coordinates":[[[16,41],[16.01,41],[16.01,41.01],[16,41.01],[16,41]]]}',
    )


def test_rows_group_by_cluster_id_and_rank_by_max_score() -> None:
    rows = [
        _row("a", 0, 0.6, "High"),
        _row("b", 0, 0.9, "VeryHigh"),
        _row("c", 1, 0.7, "High"),
    ]
    clusters = group_into_clusters(rows)
    assert len(clusters) == 2
    # ordinati per max_score decrescente
    assert clusters[0].max_score == 0.9
    assert clusters[0].cell_ids == ["b", "a"]
    assert clusters[0].dominant.cell_id == "b"
    assert clusters[1].cell_ids == ["c"]


def test_bbox_is_union_of_member_cells() -> None:
    clusters = group_into_clusters([_row("a", 0, 0.6, "High")])
    minx, miny, maxx, maxy = clusters[0].bbox
    assert minx == 16.0 and maxy == 41.01
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_report_clustering.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementare `clustering.py`**

```python
# src/limen/report/clustering.py
"""Cluster di celle contigue High+ via PostGIS ST_ClusterDBSCAN.

La query gira su mv_latest_risk (geom + factors + livello già insieme).
Il raggruppamento in Cluster è puro e testabile senza DB.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from limen.core.models.risk import RiskLevel
from limen.data.db import acquire

_CLUSTER_SQL = """
SELECT ST_ClusterDBSCAN(centroid, eps := $2, minpoints := 1) OVER () AS cluster_id,
       cell_id, aoi_id, risk_score AS score, risk_level AS level,
       factors,
       ST_X(centroid) AS lon, ST_Y(centroid) AS lat,
       ST_AsGeoJSON(geom) AS geom_json
FROM   mv_latest_risk
WHERE  aoi_id = $1 AND risk_level = ANY($3::text[])
"""


@dataclass(frozen=True)
class ClusterRow:
    cluster_id: int
    cell_id: str
    aoi_id: str
    score: float
    level: str
    s: float
    m: float
    e: float
    f: float
    h: float
    lon: float
    lat: float
    geom_json: str


@dataclass(frozen=True)
class Cluster:
    cluster_id: int
    aoi_id: str
    cell_ids: list[str]
    rows: list[ClusterRow]
    max_score: float
    dominant: ClusterRow
    bbox: tuple[float, float, float, float]  # minx, miny, maxx, maxy


def _bbox_of(rows: list[ClusterRow]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for r in rows:
        coords = json.loads(r.geom_json)["coordinates"]
        # Polygon → [ring][point][x,y]; scorri tutti i punti dell'anello esterno
        for x, y in coords[0]:
            xs.append(x)
            ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys))


def group_into_clusters(rows: list[ClusterRow]) -> list[Cluster]:
    by_id: dict[int, list[ClusterRow]] = {}
    for r in rows:
        by_id.setdefault(r.cluster_id, []).append(r)
    clusters: list[Cluster] = []
    for cid, members in by_id.items():
        members_sorted = sorted(members, key=lambda r: r.score, reverse=True)
        clusters.append(
            Cluster(
                cluster_id=cid,
                aoi_id=members_sorted[0].aoi_id,
                cell_ids=[r.cell_id for r in members_sorted],
                rows=members_sorted,
                max_score=members_sorted[0].score,
                dominant=members_sorted[0],
                bbox=_bbox_of(members_sorted),
            )
        )
    return sorted(clusters, key=lambda c: c.max_score, reverse=True)


def _levels_at_least(minimum: RiskLevel) -> list[str]:
    order = [
        RiskLevel.None_, RiskLevel.Low, RiskLevel.Moderate,
        RiskLevel.High, RiskLevel.VeryHigh,
    ]
    idx = order.index(minimum)
    return [lv.value for lv in order[idx:]]


async def load_clusters(
    aoi_id: str, *, eps_deg: float, min_level: RiskLevel
) -> list[Cluster]:
    async with acquire() as conn:
        records = await conn.fetch(
            _CLUSTER_SQL, aoi_id, eps_deg, _levels_at_least(min_level)
        )
    rows = [
        ClusterRow(
            cluster_id=int(r["cluster_id"]),
            cell_id=str(r["cell_id"]),
            aoi_id=str(r["aoi_id"]),
            score=float(r["score"]),
            level=str(r["level"]),
            s=float(_f(r["factors"], "s")),
            m=float(_f(r["factors"], "m")),
            e=float(_f(r["factors"], "e")),
            f=float(_f(r["factors"], "f")),
            h=float(_f(r["factors"], "h")),
            lon=float(r["lon"]),
            lat=float(r["lat"]),
            geom_json=str(r["geom_json"]),
        )
        for r in records
    ]
    return group_into_clusters(rows)


def _f(factors: object, key: str) -> float:
    data = factors if isinstance(factors, dict) else json.loads(str(factors))
    return float(data.get(key, 0.0))
```

- [ ] **Step 4: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_report_clustering.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add src/limen/report/clustering.py tests/unit/test_report_clustering.py
git commit -m "feat(report): PostGIS DBSCAN clustering of contiguous high-risk cells"
```

---

## Task 5: Matematica slippy-map (pure)

**Files:**
- Create: `src/limen/report/geo.py`
- Test: `tests/unit/test_report_geo.py`

- [ ] **Step 1: Scrivere il test**

```python
# tests/unit/test_report_geo.py
from limen.report.geo import lonlat_to_pixel, tile_range_for_bbox, zoom_for_bbox


def test_lonlat_to_pixel_origin() -> None:
    # (lon=-180, lat≈85.05) è il pixel (0,0) del mondo a qualsiasi zoom
    x, y = lonlat_to_pixel(-180.0, 85.0511287798066, zoom=0)
    assert round(x) == 0
    assert round(y) == 0


def test_tile_range_covers_bbox() -> None:
    z = zoom_for_bbox((16.0, 41.0, 16.2, 41.2), width_px=800, height_px=600)
    (x0, y0, x1, y1) = tile_range_for_bbox((16.0, 41.0, 16.2, 41.2), z)
    assert x0 <= x1 and y0 <= y1
    assert 0 <= z <= 19
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_report_geo.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementare `geo.py`**

```python
# src/limen/report/geo.py
"""Matematica Web Mercator / slippy-map per comporre il basemap raster.

Formule standard OSM (tile 256px). Nessuna dipendenza esterna.
"""

from __future__ import annotations

import math

TILE = 256


def lonlat_to_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Pixel globali (0,0 in alto-sinistra) alla scala ``zoom``."""
    n = TILE * (2**zoom)
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(max(min(lat, 85.05112878), -85.05112878))
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return (x, y)


def zoom_for_bbox(
    bbox: tuple[float, float, float, float], *, width_px: int, height_px: int
) -> int:
    """Massimo zoom per cui il bbox (con margine 20%) sta nel canvas."""
    minx, miny, maxx, maxy = bbox
    pad_x = (maxx - minx) * 0.2 or 0.01
    pad_y = (maxy - miny) * 0.2 or 0.01
    minx, maxx = minx - pad_x, maxx + pad_x
    miny, maxy = miny - pad_y, maxy + pad_y
    for z in range(19, -1, -1):
        x0, _ = lonlat_to_pixel(minx, maxy, z)
        x1, _ = lonlat_to_pixel(maxx, miny, z)
        _, y0 = lonlat_to_pixel(minx, maxy, z)
        _, y1 = lonlat_to_pixel(maxx, miny, z)
        if (x1 - x0) <= width_px and (y1 - y0) <= height_px:
            return z
    return 0


def tile_range_for_bbox(
    bbox: tuple[float, float, float, float], zoom: int
) -> tuple[int, int, int, int]:
    """Indici tile (x0,y0,x1,y1) che coprono il bbox allo zoom dato."""
    minx, miny, maxx, maxy = bbox
    px0, py0 = lonlat_to_pixel(minx, maxy, zoom)
    px1, py1 = lonlat_to_pixel(maxx, miny, zoom)
    return (
        int(px0 // TILE),
        int(py0 // TILE),
        int(px1 // TILE),
        int(py1 // TILE),
    )
```

- [ ] **Step 4: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_report_geo.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add src/limen/report/geo.py tests/unit/test_report_geo.py
git commit -m "feat(report): Web Mercator slippy-map math"
```

---

## Task 6: Snapshot mappa (PNG raster + fallback SVG)

**Files:**
- Create: `src/limen/report/snapshot.py`
- Test: `tests/unit/test_report_snapshot.py`

Pillow è nel gruppo `report` (optional): import guardato dentro le funzioni. Se manca (o il fetch tile fallisce), fallback a SVG puro → il report esce comunque (degradazione neutra).

- [ ] **Step 1: Scrivere il test (proiezione poligoni + fallback SVG)**

```python
# tests/unit/test_report_snapshot.py
from limen.report.snapshot import cell_svg_fallback, project_ring


def test_project_ring_maps_into_canvas() -> None:
    ring = [(16.0, 41.0), (16.1, 41.0), (16.1, 41.1), (16.0, 41.1)]
    bbox = (16.0, 41.0, 16.1, 41.1)
    pts = project_ring(ring, bbox=bbox, width=400, height=400)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert min(xs) >= 0 and max(xs) <= 400
    assert min(ys) >= 0 and max(ys) <= 400


def test_svg_fallback_contains_polygon_and_color() -> None:
    svg = cell_svg_fallback(
        [(
            [(16.0, 41.0), (16.1, 41.0), (16.1, 41.1), (16.0, 41.1)],
            "#bd0026",
        )],
        bbox=(16.0, 41.0, 16.1, 41.1),
        width=400,
        height=400,
    )
    assert svg.startswith("<svg")
    assert "polygon" in svg
    assert "#bd0026" in svg
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_report_snapshot.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementare `snapshot.py`**

```python
# src/limen/report/snapshot.py
"""Snapshot mappa per cluster: basemap raster + celle colorate → PNG.

Fallback SVG puro se Pillow manca o il fetch tile fallisce (degradazione
neutra: il report esce sempre). Attribuzione basemap impressa nel PNG.
"""

from __future__ import annotations

import json
from pathlib import Path

from limen.core.logging import get_logger
from limen.report.geo import TILE, lonlat_to_pixel, tile_range_for_bbox, zoom_for_bbox

log = get_logger(__name__)

_W = 800
_H = 600


def _padded_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bbox
    px = (maxx - minx) * 0.2 or 0.01
    py = (maxy - miny) * 0.2 or 0.01
    return (minx - px, miny - py, maxx + px, maxy + py)


def project_ring(
    ring: list[tuple[float, float]],
    *,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> list[tuple[float, float]]:
    """Proietta un anello lon/lat in pixel del canvas (Web Mercator lineare)."""
    minx, miny, maxx, maxy = _padded_bbox(bbox)
    x0, _ = lonlat_to_pixel(minx, maxy, 12)
    x1, _ = lonlat_to_pixel(maxx, miny, 12)
    _, y0 = lonlat_to_pixel(minx, maxy, 12)
    _, y1 = lonlat_to_pixel(maxx, miny, 12)
    span_x = (x1 - x0) or 1.0
    span_y = (y1 - y0) or 1.0
    out: list[tuple[float, float]] = []
    for lon, lat in ring:
        px, py = lonlat_to_pixel(lon, lat, 12)
        out.append(((px - x0) / span_x * width, (py - y0) / span_y * height))
    return out


def cell_svg_fallback(
    cells: list[tuple[list[tuple[float, float]], str]],
    *,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}">',
             f'<rect width="{width}" height="{height}" fill="#eef1f4"/>']
    for ring, color in cells:
        pts = project_ring(ring, bbox=bbox, width=width, height=height)
        pstr = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f'<polygon points="{pstr}" fill="{color}" fill-opacity="0.65" '
                     f'stroke="#333" stroke-width="0.5"/>')
    parts.append("</svg>")
    return "".join(parts)


def _rings_from_geojson(geom_json: str) -> list[list[tuple[float, float]]]:
    geom = json.loads(geom_json)
    coords = geom["coordinates"]
    if geom["type"] == "Polygon":
        return [[(x, y) for x, y in coords[0]]]
    # MultiPolygon
    return [[(x, y) for x, y in poly[0]] for poly in coords]


async def render_cluster_png(
    *,
    out_path: Path,
    bbox: tuple[float, float, float, float],
    colored_cells: list[tuple[str, str]],  # (geom_json, hex_color)
    basemap_url_template: str,
    attribution: str,
) -> bool:
    """Compone basemap raster + celle in un PNG. Ritorna True se PNG, False se
    è stato scritto il fallback SVG (accanto, con estensione .svg)."""
    cells_rings: list[tuple[list[tuple[float, float]], str]] = []
    for geom_json, color in colored_cells:
        for ring in _rings_from_geojson(geom_json):
            cells_rings.append((ring, color))

    try:
        from io import BytesIO

        from PIL import Image, ImageDraw

        from limen.integrations._http import fetch_with_retry

        pb = _padded_bbox(bbox)
        zoom = zoom_for_bbox(bbox, width_px=_W, height_px=_H)
        tx0, ty0, tx1, ty1 = tile_range_for_bbox(pb, zoom)
        canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE), "#eef1f4")
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                url = basemap_url_template.format(z=zoom, x=tx, y=ty)
                data = await fetch_with_retry(url)
                if data is None:
                    continue
                tile_img = Image.open(BytesIO(data)).convert("RGB")
                canvas.paste(tile_img, ((tx - tx0) * TILE, (ty - ty0) * TILE))

        # crop al bbox
        px_min, py_min = lonlat_to_pixel(pb[0], pb[3], zoom)
        px_max, py_max = lonlat_to_pixel(pb[2], pb[1], zoom)
        left, top = px_min - tx0 * TILE, py_min - ty0 * TILE
        cropped = canvas.crop((int(left), int(top), int(left + (px_max - px_min)),
                               int(top + (py_max - py_min)))).resize((_W, _H))

        overlay = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for ring, color in cells_rings:
            pts = project_ring(ring, bbox=bbox, width=_W, height=_H)
            rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            draw.polygon(pts, fill=(*rgb, 165), outline=(60, 60, 60, 255))
        cropped = cropped.convert("RGBA")
        cropped.alpha_composite(overlay)
        draw2 = ImageDraw.Draw(cropped)
        draw2.text((6, _H - 16), attribution, fill=(60, 60, 60, 255))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.convert("RGB").save(out_path, "PNG")
        return True
    except Exception as exc:  # noqa: BLE001 — degradazione neutra
        log.info("report.snapshot.degraded", error=str(exc), out=str(out_path))
        svg = cell_svg_fallback(cells_rings, bbox=bbox, width=_W, height=_H)
        svg_path = out_path.with_suffix(".svg")
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(svg, encoding="utf-8")
        return False
```

Nota: `fetch_with_retry` deve restituire i bytes della risposta o `None`. Se la firma reale differisce (vedi `src/limen/integrations/_http.py:110`), adatta la chiamata mantenendo il `try/except` che garantisce il fallback SVG.

- [ ] **Step 4: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_report_snapshot.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add src/limen/report/snapshot.py tests/unit/test_report_snapshot.py
git commit -m "feat(report): map snapshot (raster basemap + cells, SVG fallback)"
```

---

## Task 7: Rendering HTML (Jinja2 + template)

**Files:**
- Create: `src/limen/report/render.py`
- Create: `src/limen/report/templates/report.html.j2`
- Test: `tests/unit/test_report_render.py`

- [ ] **Step 1: Scrivere il test**

```python
# tests/unit/test_report_render.py
from limen.core.models.risk import RiskLevel
from limen.report.render import ReportView, ClusterView, render_html


def _view() -> ReportView:
    return ReportView(
        title="Limen — Zone a rischio",
        valuation_time="2026-07-11T08:00:00Z",
        pipeline_version="v1",
        national_summary="Quadro nazionale di prova.",
        clusters=[
            ClusterView(
                cluster_id=0,
                aoi_id="puglia",
                level=RiskLevel.VeryHigh,
                level_label="Molto alto",
                level_color="#bd0026",
                max_score=0.91,
                n_cells=4,
                image_rel="assets/cluster-0.png",
                reason="Il punteggio nasce soprattutto dalla pioggia.",
                verdict_text="Da attenzionare: rischio alto.",
                verdict_tone="warn",
                components=[("Versante", 0.5, "#8c6d31"), ("Pioggia", 0.8, "#1f77b4")],
            )
        ],
    )


def test_render_produces_html_with_cluster_and_palette() -> None:
    html = render_html(_view())
    assert "<!doctype html>" in html.lower() or "<html" in html.lower()
    assert "assets/cluster-0.png" in html
    assert "#bd0026" in html
    assert "Molto alto" in html
    assert "Da attenzionare" in html


def test_render_escapes_text() -> None:
    view = _view()
    view.national_summary = "<script>alert(1)</script>"
    html = render_html(view)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_report_render.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Creare il template**

```jinja
{# src/limen/report/templates/report.html.j2 #}
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ view.title }}</title>
<style>
  :root { color-scheme: light; }
  body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         color: #1a1a1a; background: #f5f6f8; }
  header { background: #1a2733; color: #fff; padding: 1.5rem 2rem; }
  header h1 { margin: 0 0 .25rem; font-size: 1.4rem; }
  header .meta { opacity: .8; font-size: .85rem; }
  main { max-width: 960px; margin: 0 auto; padding: 1.5rem 2rem 3rem; }
  .national { background: #fff; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.5rem;
              box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  .cluster { background: #fff; border-radius: 10px; overflow: hidden; margin-bottom: 1.5rem;
             box-shadow: 0 1px 6px rgba(0,0,0,.1); }
  .cluster img { width: 100%; display: block; }
  .cluster .body { padding: 1rem 1.25rem; }
  .badge { display: inline-block; padding: .15rem .6rem; border-radius: 999px; color: #fff;
           font-size: .8rem; font-weight: 600; }
  .verdict { margin: .5rem 0; font-weight: 600; }
  .verdict-warn { color: #bd0026; } .verdict-watch { color: #b8860b; } .verdict-ok { color: #2e7d32; }
  .bars { margin-top: .75rem; }
  .bar { display: flex; align-items: center; gap: .5rem; margin: .2rem 0; font-size: .8rem; }
  .bar .track { flex: 1; height: 8px; background: #eceef1; border-radius: 4px; overflow: hidden; }
  .bar .fill { height: 100%; }
  .legend { display: flex; flex-wrap: wrap; gap: .75rem; margin-top: 1rem; font-size: .8rem; }
  .legend span { display: inline-flex; align-items: center; gap: .3rem; }
  .legend .sw { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }
</style>
</head>
<body>
<header>
  <h1>{{ view.title }}</h1>
  <div class="meta">Valutazione: {{ view.valuation_time }} · pipeline {{ view.pipeline_version }}</div>
</header>
<main>
  <section class="national"><p>{{ view.national_summary }}</p></section>

  {% for c in view.clusters %}
  <article class="cluster">
    <img src="{{ c.image_rel }}" alt="Mappa cluster {{ c.cluster_id }} ({{ c.aoi_id }})">
    <div class="body">
      <span class="badge" style="background: {{ c.level_color }}">{{ c.level_label }}</span>
      <span> · {{ c.aoi_id }} · {{ c.n_cells }} celle · score {{ '%.2f'|format(c.max_score) }}</span>
      <p class="verdict verdict-{{ c.verdict_tone }}">{{ c.verdict_text }}</p>
      <p>{{ c.reason }}</p>
      <div class="bars">
        {% for label, value, color in c.components %}
        <div class="bar"><span>{{ label }}</span>
          <span class="track"><span class="fill" style="width: {{ (value*100)|round(0, 'floor') }}%; background: {{ color }}"></span></span>
        </div>
        {% endfor %}
      </div>
    </div>
  </article>
  {% endfor %}

  <div class="legend">
    {% for rc in classes %}
    <span><span class="sw" style="background: {{ rc.color }}"></span>{{ rc.label_it }} ({{ '%.2f'|format(rc.range[0]) }}–{{ '%.2f'|format(rc.range[1]) }})</span>
    {% endfor %}
  </div>
</main>
</body>
</html>
```

- [ ] **Step 4: Implementare `render.py`**

```python
# src/limen/report/render.py
"""Rendering HTML del report con Jinja2 (autoescape attivo)."""

from __future__ import annotations

from dataclasses import dataclass, field

from jinja2 import Environment, PackageLoader, select_autoescape

from limen.core.models.risk import RiskLevel
from limen.report.palette import RISK_CLASSES

_env = Environment(
    loader=PackageLoader("limen.report", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


@dataclass
class ClusterView:
    cluster_id: int
    aoi_id: str
    level: RiskLevel
    level_label: str
    level_color: str
    max_score: float
    n_cells: int
    image_rel: str
    reason: str
    verdict_text: str
    verdict_tone: str
    components: list[tuple[str, float, str]]


@dataclass
class ReportView:
    title: str
    valuation_time: str
    pipeline_version: str
    national_summary: str
    clusters: list[ClusterView] = field(default_factory=list)


def render_html(view: ReportView) -> str:
    template = _env.get_template("report.html.j2")
    return template.render(view=view, classes=RISK_CLASSES)
```

- [ ] **Step 5: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_report_render.py -v`
Expected: PASS (2 test).

- [ ] **Step 6: Commit**

```bash
git add src/limen/report/render.py src/limen/report/templates/report.html.j2 tests/unit/test_report_render.py
git commit -m "feat(report): Jinja2 HTML rendering + template"
```

---

## Task 8: Archivio immutabile + manifest + retention

**Files:**
- Create: `src/limen/report/archive.py`
- Test: `tests/unit/test_report_archive.py`

- [ ] **Step 1: Scrivere il test**

```python
# tests/unit/test_report_archive.py
import json

from limen.report.archive import prune_archive, write_build


def test_write_build_is_immutable_and_updates_pointer(tmp_path) -> None:
    root = tmp_path / "report"
    manifest = {"valuation_time": "2026-07-11T08:00:00Z", "assessment_sha256": "abc",
                "clusters": [{"cluster_id": 0, "cell_ids": ["a"]}]}
    d1 = write_build(root, build_id="2026-07-11T0800Z", html="<html>v1</html>",
                      assets={}, manifest=manifest)
    d2 = write_build(root, build_id="2026-07-11T0900Z", html="<html>v2</html>",
                     assets={}, manifest={**manifest, "assessment_sha256": "def"})
    # versione precedente intatta
    assert (d1 / "index.html").read_text() == "<html>v1</html>"
    assert json.loads((d1 / "manifest.json").read_text())["assessment_sha256"] == "abc"
    # puntatore aggiornato all'ultimo
    assert "2026-07-11T0900Z" in (root / "index.html").read_text()
    # indice timeline contiene entrambi
    idx = json.loads((root / "archive" / "index.json").read_text())
    assert len(idx["builds"]) == 2


def test_prune_keeps_manifests_but_trims_old_html(tmp_path) -> None:
    root = tmp_path / "report"
    for i in range(5):
        write_build(root, build_id=f"b{i}", html="<html></html>", assets={},
                    manifest={"assessment_sha256": str(i), "clusters": []})
    prune_archive(root, keep=2)
    remaining_html = list((root / "archive").glob("b*/index.html"))
    remaining_manifest = list((root / "archive").glob("b*/manifest.json"))
    assert len(remaining_html) == 2
    assert len(remaining_manifest) == 5  # manifest mai potati
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_report_archive.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementare `archive.py`**

```python
# src/limen/report/archive.py
"""Output versionato immutabile del report + indice timeline + retention.

Ogni build va in report/archive/<build_id>/ e NON viene mai riscritto.
Solo report/index.html (redirect) e report/archive/index.json sono mutabili.
I manifest.json non vengono mai potati (dataset per il fact-checking).
"""

from __future__ import annotations

import json
from pathlib import Path

_REDIRECT = (
    '<!doctype html><meta charset="utf-8">'
    '<meta http-equiv="refresh" content="0; url=archive/{build_id}/index.html">'
    '<a href="archive/{build_id}/index.html">Ultimo report</a>'
)


def write_build(
    root: Path,
    *,
    build_id: str,
    html: str,
    assets: dict[str, bytes],
    manifest: dict[str, object],
) -> Path:
    """Scrive un build immutabile; aggiorna puntatore + indice. Ritorna la dir."""
    build_dir = root / "archive" / build_id
    (build_dir / "assets").mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text(html, encoding="utf-8")
    (build_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, data in assets.items():
        (build_dir / "assets" / name).write_bytes(data)

    (root / "index.html").write_text(
        _REDIRECT.format(build_id=build_id), encoding="utf-8"
    )
    _update_index(root, build_id, manifest)
    return build_dir


def _update_index(root: Path, build_id: str, manifest: dict[str, object]) -> None:
    idx_path = root / "archive" / "index.json"
    builds: list[dict[str, object]] = []
    if idx_path.exists():
        builds = json.loads(idx_path.read_text())["builds"]
    builds = [b for b in builds if b.get("build_id") != build_id]
    clusters = manifest.get("clusters", [])
    builds.append(
        {
            "build_id": build_id,
            "valuation_time": manifest.get("valuation_time"),
            "assessment_sha256": manifest.get("assessment_sha256"),
            "n_clusters": len(clusters) if isinstance(clusters, list) else 0,
        }
    )
    builds.sort(key=lambda b: str(b["build_id"]))
    idx_path.write_text(
        json.dumps({"builds": builds}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def prune_archive(root: Path, *, keep: int) -> None:
    """Pota HTML+PNG dei build più vecchi oltre ``keep``; i manifest restano."""
    build_dirs = sorted(
        (p for p in (root / "archive").glob("*") if p.is_dir()),
        key=lambda p: p.name,
    )
    for old in build_dirs[:-keep] if keep < len(build_dirs) else []:
        html = old / "index.html"
        if html.exists():
            html.unlink()
        assets = old / "assets"
        if assets.exists():
            for f in assets.glob("*"):
                f.unlink()
            assets.rmdir()
```

- [ ] **Step 4: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_report_archive.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add src/limen/report/archive.py tests/unit/test_report_archive.py
git commit -m "feat(report): immutable versioned archive + manifest + retention"
```

---

## Task 9: Builder (orchestratore + idempotenza)

**Files:**
- Create: `src/limen/report/builder.py`
- Modify: `src/limen/report/__init__.py`
- Test: `tests/unit/test_report_builder.py`

- [ ] **Step 1: Scrivere il test dell'idempotenza (con dipendenze iniettate)**

```python
# tests/unit/test_report_builder.py
from limen.report.builder import build_id_for, assessment_signature


def test_signature_is_stable_and_order_independent() -> None:
    a = {"cells": [{"cell_id": "a", "score": 0.5}, {"cell_id": "b", "score": 0.9}]}
    b = {"cells": [{"cell_id": "b", "score": 0.9}, {"cell_id": "a", "score": 0.5}]}
    assert assessment_signature(a) == assessment_signature(b)


def test_build_id_from_valuation_time() -> None:
    assert build_id_for("2026-07-11T08:00:00+00:00") == "2026-07-11T0800Z"
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_report_builder.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementare `builder.py`**

```python
# src/limen/report/builder.py
"""Orchestratore del report: dati → cluster → snapshot → HTML → archivio.

Idempotente: se l'ultimo build in archivio ha la stessa firma degli assessment
correnti, salta tutto (log report.skip). Nessun richiamo LLM (usa briefing_it
già persistito). Degrada in modo neutro: uno snapshot fallito non blocca il build.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from limen.config.settings import Settings
from limen.core.logging import get_logger
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire
from limen.report.archive import prune_archive, write_build
from limen.report.clustering import Cluster, load_clusters
from limen.report.palette import color_for, label_for
from limen.report.reasons import plain_summary, verdict
from limen.report.render import ClusterView, ReportView, render_html
from limen.report.snapshot import render_cluster_png

log = get_logger(__name__)

_COMPONENTS = [
    ("Versante", "s", "#8c6d31"),
    ("Pioggia", "m", "#1f77b4"),
    ("Sisma", "e", "#9467bd"),
    ("Incendi", "f", "#d62728"),
    ("Idraulica", "h", "#17becf"),
]


def assessment_signature(payload: dict[str, object]) -> str:
    """SHA-256 su canonical-JSON (ordinato) → firma stabile order-independent."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def build_id_for(valuation_time_iso: str) -> str:
    dt = datetime.fromisoformat(valuation_time_iso)
    return dt.strftime("%Y-%m-%dT%H%MZ")


async def _latest_valuation(aoi_ids: list[str]) -> tuple[str, str, str]:
    """(valuation_time_iso, pipeline_version) dell'assessment più recente."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MAX(ra.computed_at) AS ts, MAX(ra.pipeline_version) AS pv
            FROM risk_assessments ra JOIN grid_cells g ON g.id = ra.cell_id
            WHERE g.aoi_id = ANY($1::text[])
            """,
            aoi_ids,
        )
    ts = row["ts"] if row else None
    if ts is None:
        return ("", "", "")
    return (ts.isoformat(), ts.isoformat(), str(row["pv"]))


async def _aoi_ids() -> list[str]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT id FROM aoi ORDER BY id")
    return [str(r["id"]) for r in rows]


def _last_signature(root: Path) -> str | None:
    idx = root / "archive" / "index.json"
    if not idx.exists():
        return None
    builds = json.loads(idx.read_text()).get("builds", [])
    return builds[-1].get("assessment_sha256") if builds else None


def _cluster_to_view(c: Cluster, image_rel: str) -> ClusterView:
    d = c.dominant
    level = RiskLevel(d.level)
    v = verdict(level)
    return ClusterView(
        cluster_id=c.cluster_id,
        aoi_id=c.aoi_id,
        level=level,
        level_label=label_for(level),
        level_color=color_for(level),
        max_score=c.max_score,
        n_cells=len(c.cell_ids),
        image_rel=image_rel,
        reason=plain_summary(s=d.s, m=d.m, e=d.e, f=d.f, h=d.h),
        verdict_text=v.text,
        verdict_tone=v.tone,
        components=[(lbl, getattr(d, key), col) for lbl, key, col in _COMPONENTS],
    )


async def build_report(settings: Settings | None = None) -> Path | None:
    """Costruisce (se i dati sono cambiati) un nuovo build in archivio.

    Ritorna la dir del build, o None se saltato per idempotenza / dati assenti.
    """
    settings = settings or Settings()
    cfg = settings.report
    root = Path(cfg.html_output_dir)

    aoi_ids = await _aoi_ids()
    if not aoi_ids:
        log.info("report.skip", reason="no aoi")
        return None

    all_clusters: list[Cluster] = []
    for aoi_id in aoi_ids:
        all_clusters.extend(
            await load_clusters(
                aoi_id, eps_deg=cfg.html_cluster_eps_deg, min_level=cfg.html_min_level
            )
        )
    all_clusters.sort(key=lambda c: c.max_score, reverse=True)

    valuation_iso, _, pipeline_version = await _latest_valuation(aoi_ids)
    if not valuation_iso:
        log.info("report.skip", reason="no assessment")
        return None

    signature = assessment_signature(
        {
            "valuation_time": valuation_iso,
            "clusters": [
                {"cell_ids": c.cell_ids, "max_score": round(c.max_score, 6)}
                for c in all_clusters
            ],
        }
    )
    if _last_signature(root) == signature:
        log.info("report.skip", reason="unchanged", signature=signature[:12])
        return None

    capped = all_clusters[: cfg.html_max_clusters]
    if len(all_clusters) > len(capped):
        log.info("report.cluster_cap", total=len(all_clusters), kept=len(capped))

    build_id = build_id_for(valuation_iso)
    build_dir = root / "archive" / build_id
    cluster_views: list[ClusterView] = []
    manifest_clusters: list[dict[str, object]] = []
    for c in capped:
        png_name = f"cluster-{c.cluster_id}.png"
        colored = [(r.geom_json, color_for(RiskLevel(r.level))) for r in c.rows]
        await render_cluster_png(
            out_path=build_dir / "assets" / png_name,
            bbox=c.bbox,
            colored_cells=colored,
            basemap_url_template=cfg.html_basemap_url_template,
            attribution=cfg.html_basemap_attribution,
        )
        cluster_views.append(_cluster_to_view(c, f"assets/{png_name}"))
        manifest_clusters.append(
            {
                "cluster_id": c.cluster_id,
                "aoi_id": c.aoi_id,
                "cell_ids": c.cell_ids,
                "max_score": c.max_score,
                "level": c.dominant.level,
            }
        )

    from limen.mcp.tools import national_report

    national = await national_report()
    view = ReportView(
        title="Limen — Zone a maggior rischio frana",
        valuation_time=valuation_iso,
        pipeline_version=pipeline_version,
        national_summary=str(national.get("report_it", "")),
        clusters=cluster_views,
    )
    html = render_html(view)
    manifest = {
        "valuation_time": valuation_iso,
        "pipeline_version": pipeline_version,
        "assessment_sha256": signature,
        "clusters": manifest_clusters,
    }
    # gli asset sono già scritti da render_cluster_png in build_dir/assets/;
    # write_build scrive HTML+manifest e aggiorna puntatore/indice.
    result = write_build(root, build_id=build_id, html=html, assets={}, manifest=manifest)
    prune_archive(root, keep=cfg.html_archive_keep)
    log.info("report.built", build_id=build_id, clusters=len(cluster_views))
    return result
```

Nota: `render_cluster_png` scrive i PNG direttamente in `build_dir/assets/`, quindi `write_build` è chiamato con `assets={}` (già su disco). L'idempotenza di `build_report` legge `assessment_sha256` dall'ultimo record dell'indice: `archive._update_index` (Task 8) lo registra già.

- [ ] **Step 4: Aggiornare `__init__.py`**

```python
# src/limen/report/__init__.py
"""Generatore del report HTML statico delle zone a rischio."""

from limen.report.builder import build_report

__all__ = ["build_report"]
```

- [ ] **Step 5: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_report_builder.py -v`
Expected: PASS (2 test).

- [ ] **Step 6: Commit**

```bash
git add src/limen/report/builder.py src/limen/report/__init__.py src/limen/report/archive.py tests/unit/test_report_builder.py
git commit -m "feat(report): builder orchestration with idempotency skip"
```

---

## Task 10: Job APScheduler + registrazione + kickoff al boot

**Files:**
- Create: `src/limen/api/jobs/html_report.py`
- Modify: `src/limen/api/jobs/registration.py`
- Modify: `src/limen/api/main.py:62-63`
- Test: `tests/unit/test_html_report_job.py`

- [ ] **Step 1: Scrivere il test del job (build iniettato)**

```python
# tests/unit/test_html_report_job.py
import pytest

from limen.api.jobs.html_report import run_html_report


class _Deps:
    class settings:  # noqa: N801
        class report:  # noqa: N801
            html_enabled = True


@pytest.mark.asyncio
async def test_job_swallows_errors_and_returns_status(monkeypatch) -> None:
    async def _boom(settings=None):
        raise RuntimeError("db down")

    monkeypatch.setattr("limen.api.jobs.html_report.build_report", _boom)
    result = await run_html_report(_Deps())  # non solleva
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_job_reports_built_path(monkeypatch, tmp_path) -> None:
    async def _ok(settings=None):
        return tmp_path / "archive" / "b0"

    monkeypatch.setattr("limen.api.jobs.html_report.build_report", _ok)
    result = await run_html_report(_Deps())
    assert result["ok"] is True
```

- [ ] **Step 2: Verificare il fallimento**

Run: `uv run pytest tests/unit/test_html_report_job.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementare il job**

```python
# src/limen/api/jobs/html_report.py
"""Job periodico: genera il report HTML statico (build al boot + ogni N ore).

Degrada in modo neutro: un errore nel build non deve mai far cadere lo
scheduler né lo startup. Ritorna uno status per il logging.
"""

from __future__ import annotations

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.report.builder import build_report

log = get_logger(__name__)


async def run_html_report(deps: AppDependencies) -> dict[str, object]:
    try:
        result = await build_report(deps.settings)
    except Exception as exc:  # noqa: BLE001 — job non deve mai propagare
        log.warning("job.html_report.failed", error=str(exc))
        return {"ok": False, "error": str(exc)}
    log.info("job.html_report.done", build=str(result) if result else None)
    return {"ok": True, "build": str(result) if result else None}
```

- [ ] **Step 4: Registrare il job**

In `src/limen/api/jobs/registration.py`: aggiungere l'import e la costante, poi il blocco di registrazione dopo quello del daily report (dopo riga 91).

```python
# import (in testa, dopo gli altri jobs)
from limen.api.jobs.html_report import run_html_report

# costante (dopo JOB_DAILY_REPORT, riga 32)
JOB_HTML_REPORT = "limen-html-report"

# blocco (dentro register_jobs, dopo il blocco daily_report)
    if deps.settings.report.html_enabled:
        await scheduler.add_schedule(
            run_html_report,
            args=(deps,),
            trigger=IntervalTrigger(hours=deps.settings.report.html_interval_hours),
            id=JOB_HTML_REPORT,
            conflict_policy=ConflictPolicy.replace,
            max_running_jobs=1,
        )
        registered.append(JOB_HTML_REPORT)
        log.info(
            "scheduler.registered",
            job=JOB_HTML_REPORT,
            interval_hours=deps.settings.report.html_interval_hours,
        )
```

- [ ] **Step 5: Kickoff fire-and-forget al boot**

In `src/limen/api/main.py`, nel lifespan default dopo `await scheduler.start_in_background()` (riga 63), aggiungere. `asyncio` va importato in testa se non presente.

```python
        if deps.settings.report.html_enabled and deps.settings.report.html_run_at_startup:
            async def _kickoff() -> None:
                try:
                    from limen.api.jobs.html_report import run_html_report
                    await run_html_report(deps)
                except Exception as exc:  # noqa: BLE001 — non rompe lo startup
                    log.warning("api.lifespan.report_kickoff.failed", error=str(exc))

            asyncio.create_task(_kickoff())
```

- [ ] **Step 6: Verificare il passaggio + typecheck**

Run: `uv run pytest tests/unit/test_html_report_job.py -v && uv run mypy --strict src/limen/api/jobs/html_report.py src/limen/report`
Expected: PASS (2 test), mypy clean.

- [ ] **Step 7: Commit**

```bash
git add src/limen/api/jobs/html_report.py src/limen/api/jobs/registration.py src/limen/api/main.py tests/unit/test_html_report_job.py
git commit -m "feat(report): APScheduler job + boot kickoff for HTML report"
```

---

## Task 11: CLI `limen report build`

**Files:**
- Create: `src/limen/cli/report.py`
- Modify: `src/limen/cli/main.py`
- Test: `tests/unit/test_cli_report.py`

- [ ] **Step 1: Ispezionare il dispatcher CLI**

Run: `sed -n '1,60p' src/limen/cli/main.py`
Expected: capire come i subcommand sono registrati (argparse subparsers o dict). Segui il pattern esistente (es. `monitor-once`, `backtest`).

- [ ] **Step 2: Scrivere il test**

```python
# tests/unit/test_cli_report.py
import limen.cli.report as cli_report


def test_report_command_registered() -> None:
    # il modulo espone un entrypoint invocabile
    assert hasattr(cli_report, "run")
```

- [ ] **Step 3: Implementare il subcommand**

```python
# src/limen/cli/report.py
"""`limen report build` — genera il report HTML statico una volta (idempotente)."""

from __future__ import annotations

import asyncio

from limen.config.settings import Settings
from limen.core.logging import get_logger
from limen.data.db import init_pool
from limen.report.builder import build_report

log = get_logger(__name__)


async def _run_async() -> None:
    settings = Settings()
    await init_pool(settings)  # adatta al nome reale dell'init pool in limen.data.db
    result = await build_report(settings)
    log.info("cli.report.done", build=str(result) if result else "skipped")


def run() -> None:
    asyncio.run(_run_async())
```

- [ ] **Step 4: Agganciare al dispatcher**

In `src/limen/cli/main.py`, registrare `report build` seguendo il pattern esistente degli altri subcommand (subparser `report` con azione `build` → `limen.cli.report.run`). Mantieni lo stile del file (import lazy se gli altri lo usano).

- [ ] **Step 5: Verificare il passaggio**

Run: `uv run pytest tests/unit/test_cli_report.py -v`
Expected: PASS.

- [ ] **Step 6: Verifica end-to-end contro Postgres reale (skill `verify`)**

Run (con lo stack dev su e almeno un `monitor-once` eseguito):
```bash
make up-dev && make seed
uv run limen monitor-once
uv run limen report build
```
Expected: crea `report/index.html` + `report/archive/<ts>/index.html` + `manifest.json`; un secondo `limen report build` senza nuovi assessment logga `report.skip`.

- [ ] **Step 7: Commit**

```bash
git add src/limen/cli/report.py src/limen/cli/main.py tests/unit/test_cli_report.py
git commit -m "feat(report): limen report build CLI subcommand"
```

---

## Task 12: Quality gate finale + docs env

**Files:**
- Modify: `.env.example`
- Test: intera suite

- [ ] **Step 1: Documentare i nuovi env in `.env.example`**

Aggiungere, seguendo lo stile del file (commenti sopra ogni variabile):

```bash
# --- Report HTML statico (job limen-html-report) ---
REPORT__HTML_ENABLED=true
REPORT__HTML_INTERVAL_HOURS=1        # refresh; 1 = insegue hourly_monitoring
REPORT__HTML_RUN_AT_STARTUP=true     # genera un report all'avvio dell'app
REPORT__HTML_OUTPUT_DIR=report
REPORT__HTML_MAX_CLUSTERS=50
REPORT__HTML_ARCHIVE_KEEP=240        # HTML/PNG mantenuti; i manifest.json restano sempre
# REPORT__HTML_BASEMAP_URL_TEMPLATE=https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png
REPORT__HTML_PUBLISH=false           # push su branch gh-pages (dal VPS)
```

- [ ] **Step 2: Gate qualità completo**

Run: `uv run ruff check src/limen/report && uv run ruff format --check src/limen/report && uv run mypy --strict src/limen/report && uv run pytest tests/unit -k report -v`
Expected: ruff clean, mypy clean, tutti i test report PASS.

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(report): document REPORT__HTML_* env vars"
```

---

## Note di implementazione (leggere prima di iniziare)

- **Firma reale di `fetch_with_retry`** (`src/limen/integrations/_http.py:110`): il codice di Task 6 assume che restituisca `bytes | None`. Verifica e adatta la chiamata; il `try/except` garantisce comunque il fallback SVG se la firma o la rete non collaborano.
- **`init_pool` in `limen.data.db`** (Task 11): usa il nome reale della funzione di init del pool asyncpg (allinea agli altri CLI subcommand come `monitor-once`).
- **Pubblicazione gh-pages**: fuori dallo scope di questo piano se non banale. Quando serve, aggiungere un `report/publish.py` gated da `html_publish` che fa force-push della cartella `report/` su un branch orfano `gh-pages` — è uno step git, non tocca la logica di build.
- **Nessuna migrazione SQL**: il clustering è una query a runtime su `mv_latest_risk`; nessuna modifica di schema.
- **Motivo — scelta v1 vs spec §6**: il piano usa `report_it` (nazionale, da `national_report`) + motivo deterministico per-cluster dai componenti S/M/E/F/H. Lo spec §6 elencava anche `briefing_it`/`analysis` per-AOI: sono narrativa per-AOI e non mappano 1:1 sui cluster (che il builder appiattisce cross-AOI ordinati per score). Wiring del `briefing_it` per-AOI = fast-follow opzionale se serve più narrativa; il motivo deterministico per-cluster è già specifico e dettagliato.
