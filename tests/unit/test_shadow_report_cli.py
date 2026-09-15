"""`limen shadow-report`: il confronto champion/challenger scritto su disco (#116).

Il rapporto non promuove niente, e lo dice. Quello che deve fare è non
confondere l'operatore: una finestra vuota va detta vuota, una cella senza
punteggio pre-evento va scritta come trattino e non come zero, e una data di
taglio malformata ferma il comando invece di giudicare le righe col bug.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from limen.cli import shadow_report
from limen.ml.shadow import AoiShadowStats, ShadowSummary

SINCE = datetime(2026, 7, 6, 13, tzinfo=UTC)


def _stats() -> AoiShadowStats:
    return AoiShadowStats(
        aoi_id="it-basilicata",
        aoi_name="Basilicata",
        n=240,
        mean_abs_div=0.081,
        p95_abs_div=0.212,
        max_abs_div=0.4,
        correlation=None,
        class_agreement=0.875,
        top_divergent=[("cell-1", 0.3, 0.7, 0.4)],
    )


def test_report_with_stats_and_ground_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shadow_report, "REPORTS_DIR", tmp_path)
    out = shadow_report._write_report(
        since=SINCE,
        aoi_filter="it-basilicata",
        stats=[_stats()],
        truth_rows=[
            {
                "cell_id": "cell-1",
                "aoi_id": "it-basilicata",
                "event_time": datetime(2026, 7, 20, 4, tzinfo=UTC),
                "champion_score": 0.55,
                "ml_probability": None,
            }
        ],
        model_versions=["3", "4"],
    )
    text = out.read_text(encoding="utf-8")

    assert out.name == "shadow_report_2026-07-06.md"
    assert "AOI filter: `it-basilicata` · challenger versions: 3, 4" in text
    assert "### `it-basilicata` — 240 paired runs" in text
    assert "score correlation (Pearson): **n/a**" in text
    assert "class agreement: **87.5%**" in text
    assert "| `cell-1` | 0.300 | 0.700 | +0.400 |" in text
    # Nessuna probabilità pre-evento: un trattino, non uno 0.000 inventato.
    assert "| `cell-1` | it-basilicata | 2026-07-20T04:00:00+00:00 | 0.550 | — |" in text
    assert "never promotes anything" in text


def test_report_on_an_empty_window_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shadow_report, "REPORTS_DIR", tmp_path / "nuova")
    text = shadow_report._write_report(
        since=SINCE, aoi_filter=None, stats=[], truth_rows=[], model_versions=[]
    ).read_text(encoding="utf-8")
    assert "AOI filter: `all` · challenger versions: n/a" in text
    assert "No challenger runs in the window" in text
    assert "re-run this command" in text


def _patch_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    @asynccontextmanager
    async def _pool():
        yield

    @asynccontextmanager
    async def _acquire():
        yield object()

    async def _migrations() -> None:
        seen["migrated"] = True

    async def _collect(_conn: Any, *, since: datetime, aoi_filter: str | None, with_top: bool):
        seen.update(since=since, aoi_filter=aoi_filter, with_top=with_top)
        return ShadowSummary(
            since=since,
            aoi_filter=aoi_filter,
            stats=[_stats()],
            truth_rows=[],
            model_versions=["4"],
            total_pairs=240,
        )

    monkeypatch.setattr(shadow_report, "lifespan_pool", _pool)
    monkeypatch.setattr(shadow_report, "acquire", _acquire)
    monkeypatch.setattr(shadow_report, "run_migrations", _migrations)
    monkeypatch.setattr(shadow_report, "collect_shadow_summary", _collect)
    monkeypatch.setattr(shadow_report, "REPORTS_DIR", tmp_path)
    return seen


async def test_run_reads_the_env_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_db(monkeypatch, tmp_path)
    monkeypatch.setenv("LIMEN_SHADOW_SINCE", "2026-08-01T00:00:00")
    monkeypatch.setenv("LIMEN_SHADOW_AOI", "it-puglia")

    assert await shadow_report.run() == 0

    # Una data senza fuso è UTC, non l'ora locale del container.
    assert seen["since"] == datetime(2026, 8, 1, tzinfo=UTC)
    assert seen["aoi_filter"] == "it-puglia"
    assert seen["with_top"] is True and seen["migrated"] is True
    assert (tmp_path / "shadow_report_2026-08-01.md").exists()


async def test_run_defaults_to_the_post_fix_cutoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _patch_db(monkeypatch, tmp_path)
    monkeypatch.delenv("LIMEN_SHADOW_SINCE", raising=False)
    monkeypatch.delenv("LIMEN_SHADOW_AOI", raising=False)
    assert await shadow_report.run() == 0
    assert seen["since"] == shadow_report._DEFAULT_SINCE
    assert seen["aoi_filter"] is None


async def test_a_malformed_cutoff_stops_before_judging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _patch_db(monkeypatch, tmp_path)
    monkeypatch.setenv("LIMEN_SHADOW_SINCE", "ieri")
    assert await shadow_report.run() == 1
    assert "since" not in seen
