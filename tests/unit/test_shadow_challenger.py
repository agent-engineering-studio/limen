"""V2 — ShadowChallengerExecutor never mutates authoritative state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from limen.agents.executors.shadow_challenger import ShadowChallengerExecutor
from limen.core.models.context import CellRiskRecord, MonitoringContext
from limen.core.models.risk import (
    CellFeatureBundle,
    ComponentBreakdown,
    MeteoBreakdown,
    RiskLevel,
    RiskScore,
    StaticBreakdown,
)


class _StubChallenger:
    """Returns a deterministic RiskScore for any bundle."""

    model_uri = "test://challenger"
    model_version = "v0"

    def score(self, bundle: CellFeatureBundle) -> RiskScore:
        return RiskScore(
            score=0.42,
            level=RiskLevel.Moderate,
            breakdown=ComponentBreakdown(
                s=0.4,
                m=0.4,
                e=0.0,
                f=0.0,
                h=0.0,
                static_terms=StaticBreakdown(
                    susc_ispra=0.5, iffi_density=0.0, slope=0.0, pai=0.0, litho_weight=0.0
                ),
                meteo_terms=MeteoBreakdown(
                    caine_excess=0.0, caine_norm=0.0, api_factor=0.5, soil_factor=0.5
                ),
            ),
            model_version="v0",
        )


@pytest.mark.asyncio
async def test_shadow_no_op_without_challenger() -> None:
    executor = ShadowChallengerExecutor(challenger=None)
    ctx = MonitoringContext(aoi_id="x", valuation_time=datetime(2026, 1, 1, tzinfo=UTC))
    out = await executor.run(ctx)
    assert out is ctx


@pytest.mark.asyncio
async def test_shadow_does_not_mutate_cell_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """The executor MUST return the context with cell_results untouched."""
    # Stub the model_runs repo so we don't need a real DB.
    inserted: list[Any] = []

    async def _insert_many(rows: Any) -> int:
        inserted.extend(rows)
        return len(rows)

    import limen.agents.executors.shadow_challenger as mod

    monkeypatch.setattr(mod, "insert_model_runs", _insert_many)

    executor = ShadowChallengerExecutor(_StubChallenger())
    initial_records = [
        CellRiskRecord(
            cell_id="c-1",
            score=0.7,
            level=RiskLevel.High,
            static_terms=StaticBreakdown(
                susc_ispra=0.4, iffi_density=0.0, slope=0.5, pai=0.3, litho_weight=0.1
            ),
            meteo_terms=MeteoBreakdown(
                caine_excess=0.2, caine_norm=0.3, api_factor=0.4, soil_factor=0.5
            ),
            s=0.4,
            m=0.4,
            e=0.0,
            f=0.0,
            h=0.0,
        )
    ]
    ctx = MonitoringContext(
        aoi_id="aoi-shadow",
        valuation_time=datetime(2026, 1, 1, tzinfo=UTC),
        cell_ids=("c-1",),
        cell_results=initial_records,
    )

    out = await executor.run(ctx)

    # 1. Cell results unchanged — the champion's authoritative output.
    assert out.cell_results == initial_records
    # 2. Challenger predictions persisted, tagged as challenger role.
    assert len(inserted) == 1
    assert inserted[0].role == "challenger"
    assert inserted[0].probability == pytest.approx(0.42)
    assert inserted[0].model_uri == "test://challenger"


@pytest.mark.asyncio
async def test_shadow_survives_persistence_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing insert MUST not abort the workflow."""

    async def _broken(_rows: Any) -> int:
        raise RuntimeError("DB exploded")

    import limen.agents.executors.shadow_challenger as mod

    monkeypatch.setattr(mod, "insert_model_runs", _broken)

    executor = ShadowChallengerExecutor(_StubChallenger())
    ctx = MonitoringContext(
        aoi_id="aoi",
        valuation_time=datetime(2026, 1, 1, tzinfo=UTC),
        cell_ids=("c-1",),
    )
    out = await executor.run(ctx)  # MUST NOT raise
    assert out is ctx or out == ctx
