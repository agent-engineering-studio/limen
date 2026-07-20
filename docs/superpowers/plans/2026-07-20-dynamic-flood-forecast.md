# Dynamic Flood-Forecast Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dynamic/forecast flood factor that lifts the hydrology component `H` when heavy rain is *forecast* over a hazard-prone cell, without touching the existing static H.

**Architecture:** A new pure scoring function (`flood_forecast_bonus`) computes an additive uplift = `hazard × uplift × sigmoid(forecast_72h_rain)`, tuned per macroregion in `regional_thresholds.yaml`. It's summed onto the static `flood_hazard_norm` inside the engine's `h` quota (weight `hydrology`, already 0.03). A separate opt-in executor populates the forecast rain on the bundle; when absent the factor is `0.0` and scores are byte-identical to V1. This mirrors the existing `rain_floor`/`snow` optional-block pattern.

**Tech Stack:** Python 3.12, Pydantic v2 (`_StrictModel`), pytest, the MAF `Executor`/`@handler` shim, OpenMeteo forecast client.

**Scope note:** Deterministic V0 only (Open-Meteo forecast × PGRA hazard). EFAS/CEMS and 2D hydraulic modelling are out of scope (see issue #8). The static H component is never modified. Design reference: issue #8 comment (2026-07-08).

---

## File Structure

- `src/limen/config/regional_thresholds.yaml` — new `flood_forecast` block (per-macroregion sigmoid + `hazard_uplift`).
- `src/limen/core/scoring/regional_thresholds.py` — `FloodForecastMacroregion`, `FloodForecastBlock`; optional field on `RegionalThresholds`.
- `src/limen/core/models/risk.py` — `DynamicInputs.flood_forecast_rain_72h_mm`.
- `src/limen/core/scoring/flood_forecast.py` — **new**, pure `flood_forecast_bonus(...)`.
- `src/limen/core/scoring/engine.py` — fold the bonus into `h`.
- `src/limen/config/settings.py` — `Settings.enable_flood_forecast` toggle.
- `src/limen/agents/executors/flood_forecast_fetch.py` — **new** opt-in executor.
- `src/limen/agents/executors/__init__.py` — export the executor.
- `src/limen/agents/workflows/main_workflow.py` — `add_if` the executor.
- `docs/scoring-model.md` — document the dynamic H.
- Tests: `tests/unit/test_flood_forecast.py`, additions to `tests/unit/test_scoring_engine.py` and `tests/unit/test_regional_thresholds_loader.py`.

---

## Task 1: YAML `flood_forecast` block + schema

**Files:**
- Modify: `src/limen/config/regional_thresholds.yaml`
- Modify: `src/limen/core/scoring/regional_thresholds.py`
- Test: `tests/unit/test_regional_thresholds_loader.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_regional_thresholds_loader.py`:

```python
def test_flood_forecast_block_loads_from_default_yaml() -> None:
    from limen.core.scoring.regional_thresholds import load_regional_thresholds

    t = load_regional_thresholds()
    assert t.flood_forecast is not None
    mr = t.flood_forecast.macroregions["italy_default"]
    assert mr.center_mm > 0 and mr.steepness_mm > 0
    assert 0.0 <= t.flood_forecast.hazard_uplift <= 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_regional_thresholds_loader.py::test_flood_forecast_block_loads_from_default_yaml -v`
Expected: FAIL — `t.flood_forecast` is `None` (field not defined / block missing).

- [ ] **Step 3: Add the schema models**

In `src/limen/core/scoring/regional_thresholds.py`, add near `RainFloorBlock`:

```python
class FloodForecastMacroregion(_StrictModel):
    center_mm: float = Field(..., gt=0.0)     # 72h forecast rain at sigmoid centre
    steepness_mm: float = Field(..., gt=0.0)  # sigmoid σ in mm


class FloodForecastBlock(_StrictModel):
    """Issue #8 — dynamic flood uplift on the hydrology quota. Forecast 72h
    rain × static hazard × uplift; 0 when no forecast is present."""

    hazard_uplift: float = Field(..., ge=0.0, le=5.0)
    macroregions: dict[str, FloodForecastMacroregion]

    @field_validator("macroregions")
    @classmethod
    def _has_default(
        cls, v: dict[str, FloodForecastMacroregion]
    ) -> dict[str, FloodForecastMacroregion]:
        if "italy_default" not in v:
            raise ValueError("flood_forecast.macroregions must define 'italy_default'")
        return v
```

Then add the optional field on `RegionalThresholds` (next to `rain_floor`):

```python
    # Optional (issue #8): older YAMLs without it validate; the dynamic flood
    # bonus is then 0 everywhere (H stays purely static, byte-identical to V1).
    flood_forecast: FloodForecastBlock | None = None
```

- [ ] **Step 4: Add the YAML block**

In `src/limen/config/regional_thresholds.yaml`, after the `rain_floor:` block:

```yaml
# Dynamic flood forecast (issue #8): uplift the hydrology quota H when heavy
# rain is FORECAST over a hazard-prone cell. bonus = hazard_uplift ×
# flood_hazard_norm × sigmoid((rain_72h - center)/steepness). Nessun forecast
# ⇒ bonus 0 ⇒ H puramente statico (byte-identico a V1). Regionalizzato: 72h di
# pioggia "da piena" in Puglia ≠ Liguria. Da ri-tarare su EFAS/idrometri.
flood_forecast:
  hazard_uplift: 0.5
  macroregions:
    italy_default:
      center_mm: 90.0
      steepness_mm: 35.0
    southern_italy:
      center_mm: 80.0
      steepness_mm: 30.0
    central_italy:
      center_mm: 95.0
      steepness_mm: 35.0
    northern_italy:
      center_mm: 110.0
      steepness_mm: 40.0
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_regional_thresholds_loader.py::test_flood_forecast_block_loads_from_default_yaml -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/limen/config/regional_thresholds.yaml src/limen/core/scoring/regional_thresholds.py tests/unit/test_regional_thresholds_loader.py
git commit -m "feat(scoring): flood_forecast YAML block + schema (#8)"
```

---

## Task 2: Pure `flood_forecast_bonus` function

**Files:**
- Create: `src/limen/core/scoring/flood_forecast.py`
- Test: `tests/unit/test_flood_forecast.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_flood_forecast.py`:

```python
from limen.core.scoring.flood_forecast import flood_forecast_bonus
from limen.core.scoring.regional_thresholds import (
    FloodForecastBlock,
    FloodForecastMacroregion,
)

_CFG = FloodForecastBlock(
    hazard_uplift=0.5,
    macroregions={"italy_default": FloodForecastMacroregion(center_mm=90.0, steepness_mm=35.0)},
)


def test_no_forecast_or_no_hazard_gives_zero() -> None:
    assert flood_forecast_bonus(None, 0.8, macroregion="italy_default", cfg=_CFG) == 0.0
    assert flood_forecast_bonus(150.0, None, macroregion="italy_default", cfg=_CFG) == 0.0
    assert flood_forecast_bonus(150.0, 0.0, macroregion="italy_default", cfg=_CFG) == 0.0


def test_heavy_forecast_on_hazard_cell_lifts() -> None:
    # 200 mm/72h well above centre 90 → sigmoid ~1 → bonus ≈ 0.8 * 0.5 * ~1
    bonus = flood_forecast_bonus(200.0, 0.8, macroregion="italy_default", cfg=_CFG)
    assert 0.35 < bonus <= 0.4


def test_dry_forecast_gives_near_zero() -> None:
    assert flood_forecast_bonus(5.0, 0.8, macroregion="italy_default", cfg=_CFG) < 0.05


def test_bonus_scales_with_hazard() -> None:
    high = flood_forecast_bonus(200.0, 0.9, macroregion="italy_default", cfg=_CFG)
    low = flood_forecast_bonus(200.0, 0.2, macroregion="italy_default", cfg=_CFG)
    assert high > low


def test_unknown_macroregion_falls_back_to_default() -> None:
    b = flood_forecast_bonus(200.0, 0.8, macroregion="atlantis", cfg=_CFG)
    assert b > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_flood_forecast.py -v`
Expected: FAIL — module `flood_forecast` does not exist.

- [ ] **Step 3: Write the implementation**

Create `src/limen/core/scoring/flood_forecast.py`:

```python
"""Dynamic flood uplift (issue #8).

Pure function: forecast 72h rain × static hazard × uplift, sigmoid-shaped and
macroregion-tuned. Returns an additive bonus (>= 0) for the engine's hydrology
quota H. No I/O. Returns 0.0 whenever the forecast rain or the static hazard is
missing, so a bundle without the flood feed scores byte-identical to V1.
"""

from __future__ import annotations

import math

from limen.core.scoring.regional_thresholds import FloodForecastBlock


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def flood_forecast_bonus(
    rain_72h_mm: float | None,
    flood_hazard_norm: float | None,
    *,
    macroregion: str,
    cfg: FloodForecastBlock,
) -> float:
    """Additive uplift for H: ``hazard_uplift × hazard × sigmoid(rain)``."""
    if rain_72h_mm is None or flood_hazard_norm is None or flood_hazard_norm <= 0.0:
        return 0.0
    mr = cfg.macroregions.get(macroregion) or cfg.macroregions["italy_default"]
    rain_norm = _sigmoid((rain_72h_mm - mr.center_mm) / mr.steepness_mm)
    bonus = cfg.hazard_uplift * flood_hazard_norm * rain_norm
    return bonus if bonus < 1.0 else 1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_flood_forecast.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/limen/core/scoring/flood_forecast.py tests/unit/test_flood_forecast.py
git commit -m "feat(scoring): pure flood_forecast_bonus factor (#8)"
```

---

## Task 3: Bundle field for forecast rain

**Files:**
- Modify: `src/limen/core/models/risk.py` (the `DynamicInputs` model)
- Test: `tests/unit/test_flood_forecast.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_flood_forecast.py`:

```python
def test_dynamic_inputs_accepts_flood_forecast_rain() -> None:
    from datetime import UTC, datetime

    from limen.core.models.risk import DynamicInputs

    d = DynamicInputs(
        valuation_time=datetime(2026, 6, 1, tzinfo=UTC),
        flood_forecast_rain_72h_mm=120.0,
    )
    assert d.flood_forecast_rain_72h_mm == 120.0
    # default is None so existing bundles are unaffected
    assert DynamicInputs(valuation_time=datetime(2026, 6, 1, tzinfo=UTC)).flood_forecast_rain_72h_mm is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_flood_forecast.py::test_dynamic_inputs_accepts_flood_forecast_rain -v`
Expected: FAIL — `DynamicInputs` has no field `flood_forecast_rain_72h_mm`.

- [ ] **Step 3: Add the field**

In `src/limen/core/models/risk.py`, inside `class DynamicInputs`, next to `snow_depth_m`:

```python
    # Issue #8: forecast cumulated rain over the next 72 h (mm), used by the
    # dynamic flood factor. None ⇒ dynamic flood bonus is 0 (H stays static).
    flood_forecast_rain_72h_mm: float | None = Field(default=None, ge=0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_flood_forecast.py::test_dynamic_inputs_accepts_flood_forecast_rain -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/limen/core/models/risk.py tests/unit/test_flood_forecast.py
git commit -m "feat(models): DynamicInputs.flood_forecast_rain_72h_mm (#8)"
```

---

## Task 4: Fold the bonus into the engine's H

**Files:**
- Modify: `src/limen/core/scoring/engine.py`
- Test: `tests/unit/test_scoring_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_scoring_engine.py` (the `_bundle` helper already builds bundles; extend a bundle with the forecast field via `model_copy`):

```python
def test_flood_forecast_lifts_h_only_when_rain_forecast() -> None:
    from limen.core.models.risk import StaticFactors

    static = StaticFactors(cell_id="c", flood_hazard_norm=0.8)
    dry = _bundle(static=static)  # no forecast rain
    wet = dry.model_copy(
        update={"dynamic": dry.dynamic.model_copy(update={"flood_forecast_rain_72h_mm": 200.0})}
    )
    s_dry = score(dry)
    s_wet = score(wet)
    assert s_wet.breakdown.h > s_dry.breakdown.h
    assert s_wet.score >= s_dry.score


def test_flood_forecast_absent_is_byte_identical() -> None:
    from limen.core.models.risk import StaticFactors

    b = _bundle(static=StaticFactors(cell_id="c", flood_hazard_norm=0.8))
    # No forecast rain ⇒ H equals the pure static hazard.
    assert score(b).breakdown.h == pytest.approx(0.8)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_scoring_engine.py::test_flood_forecast_lifts_h_only_when_rain_forecast -v`
Expected: FAIL — `s_wet.breakdown.h == s_dry.breakdown.h` (engine ignores the new field).

- [ ] **Step 3: Wire the bonus into the engine**

In `src/limen/core/scoring/engine.py`, add the import:

```python
from limen.core.scoring.flood_forecast import flood_forecast_bonus
```

Replace the current `h` computation in `score(...)`:

```python
        h = (
            _clamp01(bundle.static.flood_hazard_norm)
            if bundle.static.flood_hazard_norm is not None
            else 0.0
        )
```

with:

```python
        h_static = (
            _clamp01(bundle.static.flood_hazard_norm)
            if bundle.static.flood_hazard_norm is not None
            else 0.0
        )
        flood_bonus = (
            flood_forecast_bonus(
                bundle.dynamic.flood_forecast_rain_72h_mm,
                bundle.static.flood_hazard_norm,
                macroregion=bundle.macroregion,
                cfg=self._t.flood_forecast,
            )
            if self._t.flood_forecast is not None
            else 0.0
        )
        h = _clamp01(h_static + flood_bonus)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_scoring_engine.py -k "flood_forecast or byte_identical or does_not_change" -v`
Expected: PASS. The existing `test_llm_does_not_change_numeric_breakdown` and monotonicity tests must still pass.

- [ ] **Step 5: Full engine + purity check**

Run: `uv run pytest tests/unit/test_scoring_engine.py tests/unit/test_scoring_engine_flood.py -q`
Expected: PASS (no regression in the existing static-H flood test).

- [ ] **Step 6: Commit**

```bash
git add src/limen/core/scoring/engine.py tests/unit/test_scoring_engine.py
git commit -m "feat(scoring): dynamic flood bonus folds into H (#8)"
```

---

## Task 5: Settings toggle

**Files:**
- Modify: `src/limen/config/settings.py`
- Test: `tests/unit/test_settings.py` (create if absent)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_settings.py`:

```python
def test_flood_forecast_disabled_by_default() -> None:
    from limen.config.settings import Settings

    assert Settings().enable_flood_forecast is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_settings.py::test_flood_forecast_disabled_by_default -v`
Expected: FAIL — `Settings` has no attribute `enable_flood_forecast`.

- [ ] **Step 3: Add the toggle**

In `src/limen/config/settings.py`, on the top-level `Settings` class next to `enable_insitu`:

```python
    # Issue #8: opt-in dynamic flood forecast feed. Off by default so the
    # operational engine is unchanged until the feed is deployed.
    enable_flood_forecast: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_settings.py::test_flood_forecast_disabled_by_default -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/limen/config/settings.py tests/unit/test_settings.py
git commit -m "feat(config): enable_flood_forecast toggle, default off (#8)"
```

---

## Task 6: Opt-in forecast-rain executor

**Files:**
- Create: `src/limen/agents/executors/flood_forecast_fetch.py`
- Modify: `src/limen/agents/executors/__init__.py`
- Test: `tests/unit/test_flood_forecast_fetch.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_flood_forecast_fetch.py`. Mirror the existing executor tests (build a `MonitoringContext` with cells, assert the field is set; a failing client degrades to `None`):

```python
import pytest

from limen.agents.executors.flood_forecast_fetch import FloodForecastFetchExecutor


class _FakeForecastClient:
    async def forecast_72h_mm(self, lat: float, lon: float) -> float:
        return 130.0


class _DegradingClient:
    async def forecast_72h_mm(self, lat: float, lon: float) -> float:
        raise RuntimeError("open-meteo down")


@pytest.mark.asyncio
async def test_executor_sets_forecast_rain_on_cells(monitoring_ctx_with_cells) -> None:
    ctx = monitoring_ctx_with_cells  # fixture: ctx with >=1 cell bundle
    out = await FloodForecastFetchExecutor(client=_FakeForecastClient()).run(ctx)
    assert all(
        c.bundle.dynamic.flood_forecast_rain_72h_mm == 130.0 for c in out.cells
    )


@pytest.mark.asyncio
async def test_executor_degrades_to_none(monitoring_ctx_with_cells) -> None:
    ctx = monitoring_ctx_with_cells
    out = await FloodForecastFetchExecutor(client=_DegradingClient()).run(ctx)
    assert all(c.bundle.dynamic.flood_forecast_rain_72h_mm is None for c in out.cells)
```

> Note: reuse or add the `monitoring_ctx_with_cells` fixture in `tests/unit/conftest.py` following the pattern used by the existing meteo/seismic executor tests. If those tests build the context inline, do the same here (no shared fixture required).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_flood_forecast_fetch.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the executor**

Create `src/limen/agents/executors/flood_forecast_fetch.py`, following the `MeteoFetchExecutor` shape (`Executor` + `@handler`), reading the AOI's forecast 72h rain from the shared OpenMeteo client and setting the field on each cell bundle. Degrade per the invariant — any client error ⇒ leave the field `None` + `log.info("integration.degraded", op="flood_forecast", ...)`, never raise:

```python
from __future__ import annotations

from typing import Protocol

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext

log = get_logger(__name__)


class _ForecastClient(Protocol):
    async def forecast_72h_mm(self, lat: float, lon: float) -> float: ...


class FloodForecastFetchExecutor(Executor):
    """Opt-in: populate ``flood_forecast_rain_72h_mm`` on each cell bundle.

    Reuses the OpenMeteo forecast client (no new integration). Neutral
    degradation: any failure leaves the field ``None`` and logs
    ``integration.degraded`` — never raises (read path)."""

    def __init__(self, client: _ForecastClient) -> None:
        super().__init__(name="FloodForecastFetch")
        self._client = client

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        for cell in ctx.cells:
            try:
                rain = await self._client.forecast_72h_mm(
                    cell.bundle.static.lat, cell.bundle.static.lon
                )
            except Exception as exc:  # noqa: BLE001 - degrade, never raise
                log.info("integration.degraded", op="flood_forecast", error=str(exc))
                continue
            cell.bundle = cell.bundle.model_copy(
                update={
                    "dynamic": cell.bundle.dynamic.model_copy(
                        update={"flood_forecast_rain_72h_mm": rain}
                    )
                }
            )
        return ctx
```

> **Adapt to the real context shape.** Before writing this, open `src/limen/agents/executors/meteo_fetch.py` and `src/limen/core/models/context.py` to confirm how cells/bundles are stored and mutated on `MonitoringContext` (field names, whether cells carry `lat`/`lon`, how meteo writes back). Match that exactly — the snippet above assumes `ctx.cells[i].bundle` and `bundle.static.lat/lon`; fix the names to whatever meteo_fetch uses.

Export it in `src/limen/agents/executors/__init__.py` alongside the others:

```python
from limen.agents.executors.flood_forecast_fetch import FloodForecastFetchExecutor
```

and add `"FloodForecastFetchExecutor"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_flood_forecast_fetch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/limen/agents/executors/flood_forecast_fetch.py src/limen/agents/executors/__init__.py tests/unit/test_flood_forecast_fetch.py
git commit -m "feat(agents): opt-in flood_forecast_fetch executor (#8)"
```

---

## Task 7: Wire the executor into the workflow (opt-in)

**Files:**
- Modify: `src/limen/agents/workflows/main_workflow.py`
- Test: `tests/unit/test_main_workflow.py` (or the existing workflow-build test)

- [ ] **Step 1: Write the failing test**

Add to the workflow test module (mirror the `enable_insitu` toggle test already there):

```python
def test_flood_forecast_step_present_only_when_enabled() -> None:
    from limen.agents.workflows.main_workflow import build_landslide_workflow
    from limen.config.settings import Settings

    off = build_landslide_workflow(_deps(settings=Settings(enable_flood_forecast=False)))
    on = build_landslide_workflow(_deps(settings=Settings(enable_flood_forecast=True)))
    assert on.step_count == off.step_count + 1
```

> `_deps(...)` — reuse the helper/fixture the existing workflow-build tests use to construct `WorkflowDeps` with a stub LLM factory. If they build it inline, do the same.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_main_workflow.py::test_flood_forecast_step_present_only_when_enabled -v`
Expected: FAIL — step counts equal (executor not wired).

- [ ] **Step 3: Wire it with `add_if`**

In `src/limen/agents/workflows/main_workflow.py`, import the executor and the client factory, then add the conditional step **after `MeteoFetchExecutor`** (it needs the same forecast data era) and before scoring. Mirror the `SensorFetchExecutor` `add_if` block:

```python
from limen.agents.executors import FloodForecastFetchExecutor

# ... inside build_landslide_workflow, after .add(MeteoFetchExecutor(...)) and
# after the sensor add_if:
flood = FloodForecastFetchExecutor(client=_flood_forecast_client(settings))
builder = builder.add_if(
    lambda ctx: bool(getattr(ctx, "enable_flood_forecast", settings.enable_flood_forecast)),
    flood,
)
```

Add a small factory near `_default_factory()`:

```python
def _flood_forecast_client(settings: Settings) -> "FloodForecastClient":
    """Adapter over the shared OpenMeteo forecast client that returns the
    72h cumulated forecast rain for a point. Late import to keep test imports
    free of integration state."""
    from limen.integrations.openmeteo.client import build_forecast_72h_client

    return build_forecast_72h_client(settings)
```

> The adapter `build_forecast_72h_client` should wrap the existing OpenMeteo forecast fetch (already used by `MeteoFetchExecutor` / the forecast workflow) and expose `async forecast_72h_mm(lat, lon) -> float`. Implement it in `src/limen/integrations/openmeteo/client.py` reusing the existing forecast call; if a suitable method already returns an hourly forecast series, sum the next 72 h of precipitation. Keep it a thin adapter — no new HTTP integration.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_main_workflow.py::test_flood_forecast_step_present_only_when_enabled -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/limen/agents/workflows/main_workflow.py src/limen/integrations/openmeteo/client.py tests/unit/test_main_workflow.py
git commit -m "feat(agents): opt-in flood forecast step in the workflow (#8)"
```

---

## Task 8: Document the dynamic H

**Files:**
- Modify: `docs/scoring-model.md`

- [ ] **Step 1: Extend the H section**

In `docs/scoring-model.md`, under `### H — componente idraulica`, append:

```markdown
**Componente dinamica (issue #8, opt-in).** Quando il feed di previsione è
attivo (`ENABLE_FLOOD_FORECAST=true`), `H` riceve un *uplift* additivo quando
è **prevista** pioggia intensa su una cella a pericolosità idraulica:

```
bonus = hazard_uplift · flood_hazard_norm · sigmoid((rain_72h_prev - center)/steepness)
H     = clamp01(flood_hazard_norm + bonus)
```

Parametri per macroregione in `flood_forecast.macroregions.*`
(`center_mm`/`steepness_mm`) + `hazard_uplift`. Nessuna previsione ⇒ `bonus = 0`
⇒ `H` puramente statico (byte-identico a V1). La componente H statica non è
modificata; l'uplift è deterministico, puro, e la fonte esterna degrada in modo
neutro. Fonti V0: Open-Meteo forecast; upgrade EFAS/CEMS fuori scope.
```

- [ ] **Step 2: Commit**

```bash
git add docs/scoring-model.md
git commit -m "docs(scoring): document the dynamic flood component (#8)"
```

---

## Final verification

- [ ] **All quality gates green**

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run mypy --strict src/
uv run pytest tests/unit -q
```
Expected: all clean/green. Key invariants to eyeball: `test_flood_forecast_absent_is_byte_identical` passes (V1 unchanged when the feed is off), and the LLM-invariance / monotonicity tests still pass.

- [ ] **Behavioural check (optional, needs DB)**

Use the `verify` skill or a scratch script: build a `CellFeatureBundle` with `flood_hazard_norm=0.8` and `flood_forecast_rain_72h_mm=200`, score it with `enable_flood_forecast` on, and confirm `breakdown.h > 0.8` and the class did not drop.

---

## Self-review notes

- **Spec coverage:** new `flood_forecast` YAML block (Task 1) ✓; optional bundle input (Task 3) ✓; pure scoring function feeding `hydrology` (Tasks 2, 4) ✓; separate opt-in executor with neutral degradation (Tasks 6, 7) ✓; static H untouched — verified by `test_flood_forecast_absent_is_byte_identical` (Task 4) ✓; no hard-coded constants — all in YAML, proven by the loader test (Task 1) ✓; docs (Task 8) ✓.
- **Out of scope confirmed:** EFAS/CEMS, 2D hydraulics, ML variant (would follow the `limen.ml.train` promotion gate separately).
- **Type consistency:** `flood_forecast_bonus(rain_72h_mm, flood_hazard_norm, *, macroregion, cfg)` is used identically in Task 2 (def), Task 4 (engine call); the bundle field `flood_forecast_rain_72h_mm` is defined in Task 3 and read in Tasks 4/6; `FloodForecastBlock`/`FloodForecastMacroregion` defined in Task 1 and imported in Tasks 2/4.
- **Assumptions to verify at execution time (flagged inline):** the exact `MonitoringContext`/cell/bundle field names (Task 6) and the OpenMeteo forecast adapter method (Task 7) — confirm against `meteo_fetch.py` before writing, since those files weren't re-read while planning.
