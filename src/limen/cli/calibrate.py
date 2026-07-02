"""``limen calibrate`` — precompute norm stats + ``s_static`` + run S↔ISPRA gate.

Per §2.5 of the project doc:

1. Min-max normalisation per AOI over the cell subset (the factors
   normalised here are ``iffi_density_500``, ``slope_deg``, and any
   other unbounded factor — bounded factors like ``pai_class_norm`` or
   ``susc_ispra`` are already in [0, 1] and only their min/max are
   recorded for audit).
2. Compute ``s_static`` per cell using the deterministic engine's S
   sub-aggregation, persist to ``cell_static_factors.s_static``.
3. Validation gate: Pearson correlation between ``s_static`` and the
   ISPRA susceptibility class (when available in the
   ``susceptibility`` table) must be ≥ ``calibration.s_vs_ispra_correlation_min``
   (default 0.85 from the YAML).
4. Emit a short Markdown report under ``./reports/calibrate_<aoi>.md``.

Idempotent: re-running on the same data yields the same ``s_static``
and the same Markdown report (the timestamp is the only diff).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.core.models.risk import CellFeatureBundle, DynamicInputs, StaticFactors
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import acquire, lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.data.repos.norm_stats_repo import NormStat
from limen.data.repos.norm_stats_repo import upsert_many as upsert_norms

log = get_logger(__name__)

REPORTS_DIR = Path("./reports")
_FACTORS_FOR_NORM = ("iffi_density_500", "slope_deg", "pai_class_norm")


@dataclass(frozen=True, slots=True)
class _AoiCalibration:
    aoi_id: str
    cells: int
    s_correlation: float | None
    s_correlation_ok: bool
    susc_rows_available: int
    report_path: Path


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
async def _fetch_factors(aoi_id: str) -> list[dict[str, Any]]:
    """Pull the static-factor rows we need to compute S per cell."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.cell_id, c.iffi_density_500, c.slope_deg, c.pai_class_norm,
                   c.litho_weight,
                   s.score AS susc_score
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            LEFT JOIN susceptibility s ON s.cell_id = c.cell_id
            WHERE g.aoi_id = $1
            ORDER BY c.cell_id
            """,
            aoi_id,
        )
    return [dict(r) for r in rows]


async def _write_s_static(values: dict[str, float]) -> None:
    if not values:
        return
    async with acquire() as conn, conn.transaction():
        for cell_id, s in values.items():
            await conn.execute(
                """
                UPDATE cell_static_factors
                SET s_static = $1, updated_at = now()
                WHERE cell_id = $2
                """,
                s,
                cell_id,
            )


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def _min_max(values: list[float]) -> tuple[float, float]:
    return (min(values), max(values))


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; returns ``None`` if degenerate."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return sxy / math.sqrt(sxx * syy)


# ---------------------------------------------------------------------------
# Per-AOI workflow
# ---------------------------------------------------------------------------
async def _calibrate_aoi(aoi_id: str, *, strict: bool) -> _AoiCalibration:
    rows = await _fetch_factors(aoi_id)
    log.info("calibrate.aoi.rows", aoi_id=aoi_id, count=len(rows))

    if not rows:
        report_path = _write_report(
            aoi_id=aoi_id,
            cells=0,
            stats=[],
            correlation=None,
            correlation_ok=False,
            susc_rows=0,
            note="no cell_static_factors rows for this AOI — run `limen bootstrap-static` first",
        )
        return _AoiCalibration(aoi_id, 0, None, False, 0, report_path)

    thresholds = load_regional_thresholds()
    engine = MultiFactorScoringEngine(thresholds)
    model_version = thresholds.model_version

    # Min/max for each tracked factor (only over non-null observations).
    norm_stats: list[NormStat] = []
    for factor in _FACTORS_FOR_NORM:
        observations = [float(r[factor]) for r in rows if r[factor] is not None]
        if not observations:
            log.warning("calibrate.factor.empty", aoi_id=aoi_id, factor=factor)
            continue
        lo, hi = _min_max(observations)
        norm_stats.append(
            NormStat(
                aoi_id=aoi_id,
                factor=factor,
                min_value=lo,
                max_value=hi,
                model_version=model_version,
                sample_size=len(observations),
                extras={"non_null": len(observations), "total": len(rows)},
            )
        )
    await upsert_norms(norm_stats)

    # Build per-cell static factors → S via the engine.
    valuation_time = datetime.now(UTC)
    s_values: dict[str, float] = {}
    s_list: list[float] = []
    susc_list: list[float] = []
    for r in rows:
        cell_id = str(r["cell_id"])
        bundle = CellFeatureBundle(
            aoi_id=aoi_id,
            cell_id=cell_id,
            static=StaticFactors(
                cell_id=cell_id,
                iffi_density_500=(
                    float(r["iffi_density_500"]) if r["iffi_density_500"] is not None else None
                ),
                slope_deg=float(r["slope_deg"]) if r["slope_deg"] is not None else None,
                pai_class_norm=(
                    float(r["pai_class_norm"]) if r["pai_class_norm"] is not None else None
                ),
                litho_weight=float(r["litho_weight"]) if r["litho_weight"] is not None else None,
                susc_ispra=float(r["susc_score"]) if r["susc_score"] is not None else None,
            ),
            dynamic=DynamicInputs(valuation_time=valuation_time),
        )
        scored = engine.score(bundle)
        s_values[cell_id] = scored.breakdown.s
        if r["susc_score"] is not None:
            s_list.append(scored.breakdown.s)
            susc_list.append(float(r["susc_score"]))

    await _write_s_static(s_values)
    log.info(
        "calibrate.s_static.written",
        aoi_id=aoi_id,
        cells=len(s_values),
        with_susc=len(susc_list),
    )

    susc_rows = len(susc_list)
    gate_min = thresholds.calibration.s_vs_ispra_correlation_min
    correlation: float | None = None
    # gate_min is None ⇒ the S↔ISPRA gate is disabled (susceptibility dropped
    # from S). Treat it as passing so the calibration run never fails on it.
    correlation_ok = gate_min is None
    if susc_rows >= 3:
        correlation = _pearson(s_list, susc_list)
        if correlation is not None and gate_min is not None:
            correlation_ok = correlation >= gate_min

    if susc_rows < 3 and strict:
        raise RuntimeError(
            f"calibrate: insufficient ISPRA susceptibility rows ({susc_rows}) for AOI {aoi_id}; "
            "ingest the ISPRA susceptibility layer or drop --strict"
        )

    report_path = _write_report(
        aoi_id=aoi_id,
        cells=len(s_values),
        stats=norm_stats,
        correlation=correlation,
        correlation_ok=correlation_ok,
        susc_rows=susc_rows,
        note=None,
    )
    return _AoiCalibration(
        aoi_id, len(s_values), correlation, correlation_ok, susc_rows, report_path
    )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------
def _write_report(
    *,
    aoi_id: str,
    cells: int,
    stats: list[NormStat],
    correlation: float | None,
    correlation_ok: bool,
    susc_rows: int,
    note: str | None,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"calibrate_{aoi_id}.md"
    lines: list[str] = [
        f"# Limen calibration report — AOI `{aoi_id}`",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        f"- Cells calibrated: **{cells}**",
        f"- ISPRA susceptibility rows: **{susc_rows}**",
    ]
    if correlation is None:
        lines.append("- S vs ISPRA correlation: **n/a** (no susceptibility rows)")
    else:
        ok = "PASS" if correlation_ok else "FAIL"
        lines.append(f"- S vs ISPRA correlation (Pearson): **{correlation:.4f}** — gate **{ok}**")
    if note:
        lines += ["", f"> {note}", ""]

    lines += ["", "## Normalisation statistics", ""]
    if stats:
        lines += ["| Factor | min | max | sample |", "|---|---|---|---|"]
        for s in stats:
            lines.append(
                f"| `{s.factor}` | {s.min_value:.4f} | {s.max_value:.4f} | {s.sample_size or 0} |"
            )
    else:
        lines.append("_No normalisation statistics recorded (no observations)._")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------
async def run() -> int:
    """Run calibration for every seeded AOI.

    Set ``LIMEN_CALIBRATE_STRICT=1`` to make missing ISPRA susceptibility
    data a fatal error rather than a logged warning.
    """
    strict = os.getenv("LIMEN_CALIBRATE_STRICT", "").strip().lower() in {"1", "true", "yes"}

    async with lifespan_pool():
        await run_migrations()
        aois = await list_aoi_ids()
        if not aois:
            log.warning("calibrate.no_aois", note="run `limen seed` first")
            return 0

        exit_code = 0
        thresholds = load_regional_thresholds()
        for aoi_id in aois:
            cal = await _calibrate_aoi(aoi_id, strict=strict)
            log.info(
                "calibrate.aoi.done",
                aoi_id=cal.aoi_id,
                cells=cal.cells,
                susc_rows=cal.susc_rows_available,
                s_correlation=cal.s_correlation,
                gate=cal.s_correlation_ok,
                report=str(cal.report_path),
            )
            if cal.susc_rows_available >= 3 and not cal.s_correlation_ok:
                log.error(
                    "calibrate.gate.failed",
                    aoi_id=cal.aoi_id,
                    correlation=cal.s_correlation,
                    threshold=thresholds.calibration.s_vs_ispra_correlation_min,
                )
                exit_code = 1
        return exit_code


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
