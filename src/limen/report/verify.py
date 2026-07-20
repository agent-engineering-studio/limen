"""Fact-checking of archived report zones against real landslide events (#17).

Each archived build (``<html_output_dir>/archive/<build_id>/manifest.json``) is
an immutable record of the zones the report flagged at ``valuation_time``. Once
the horizon has elapsed we check, a posteriori, whether landslides actually
occurred in those zones — producing **hit / false_alarm / miss** labels and
POD / FAR / lead-time, and enriching the supervised dataset for calibration.

The labelling + metrics are a **pure** function (``summarize_build``), unit-
tested on fixtures. The spatial/temporal join against ``landslide_events`` and
the file I/O are the shell. Neutral degradation: no events ⇒ no verification,
never an error. Idempotent: a build with a ``verification.json`` is skipped.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ZoneOutcome:
    cluster_id: int
    aoi_id: str
    n_cells: int
    outcome: str  # "hit" | "false_alarm"
    matched_event_ids: list[str] = field(default_factory=list)
    min_distance_m: float | None = None


@dataclass(frozen=True, slots=True)
class BuildOutcome:
    build_id: str
    valuation_time: str
    horizon_h: int
    shown_level: str
    zones: list[ZoneOutcome]
    miss_event_ids: list[str]
    pod: float  # detected events / all AOI events in the window
    far: float  # false-alarm zones / all zones
    mean_lead_time_h: float | None
    verified_at: str


# Zones with no cells can't match anything; treat as false_alarm by definition.
def summarize_build(
    *,
    build_id: str,
    valuation_time: str,
    horizon_h: int,
    shown_level: str,
    clusters: list[dict[str, Any]],
    matched_by_cluster: dict[int, list[str]],
    aoi_event_ids: set[str],
    lead_hours_by_event: dict[str, float],
    min_dist_by_cluster: dict[int, float],
    verified_at: str,
) -> BuildOutcome:
    """Label each zone hit/false_alarm, find misses, compute POD/FAR/lead-time.

    Pure: all spatial matching is pre-computed by the caller and passed in.
    """
    zones: list[ZoneOutcome] = []
    matched_events: set[str] = set()
    for c in clusters:
        cid = int(c["cluster_id"])
        matched = list(matched_by_cluster.get(cid, []))
        matched_events.update(matched)
        zones.append(
            ZoneOutcome(
                cluster_id=cid,
                aoi_id=str(c["aoi_id"]),
                n_cells=len(c.get("cell_ids", [])),
                outcome="hit" if matched else "false_alarm",
                matched_event_ids=sorted(matched),
                min_distance_m=min_dist_by_cluster.get(cid),
            )
        )

    misses = sorted(aoi_event_ids - matched_events)
    n_zones = len(zones)
    false_alarms = sum(1 for z in zones if z.outcome == "false_alarm")
    pod = len(matched_events) / len(aoi_event_ids) if aoi_event_ids else 0.0
    far = false_alarms / n_zones if n_zones else 0.0

    lead_vals = [lead_hours_by_event[e] for e in matched_events if e in lead_hours_by_event]
    mean_lead = sum(lead_vals) / len(lead_vals) if lead_vals else None

    return BuildOutcome(
        build_id=build_id,
        valuation_time=valuation_time,
        horizon_h=horizon_h,
        shown_level=shown_level,
        zones=zones,
        miss_event_ids=misses,
        pod=pod,
        far=far,
        mean_lead_time_h=mean_lead,
        verified_at=verified_at,
    )


_ZONE_MATCH_SQL = """
SELECT e.id AS event_id,
       e.event_time AS event_time,
       MIN(ST_Distance(ST_Transform(e.geom, 3035), ST_Transform(g.geom, 3035))) AS dist_m
FROM landslide_events e
JOIN grid_cells g ON g.id = ANY($1::text[])
WHERE e.event_time > $2 AND e.event_time <= $3
  AND ST_DWithin(ST_Transform(e.geom, 3035), ST_Transform(g.geom, 3035), $4)
GROUP BY e.id, e.event_time
"""

_AOI_EVENTS_SQL = """
SELECT e.id AS event_id, e.event_time AS event_time
FROM landslide_events e
JOIN aoi a ON ST_Intersects(a.geom, e.geom)
WHERE a.id = ANY($1::text[]) AND e.event_time > $2 AND e.event_time <= $3
"""


def _read_manifest(build_dir: Path) -> dict[str, Any] | None:
    path = build_dir / "manifest.json"
    if not path.exists():
        return None
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        log.warning("verify.manifest.unreadable", build=str(build_dir))
        return None


async def verify_build(
    conn: Any,
    build_dir: Path,
    *,
    horizon_h: int,
    grace_h: int,
    radius_m: float,
    now: datetime,
) -> BuildOutcome | None:
    """Verify one archived build. Returns None when skipped (idempotent / too
    early / unreadable)."""
    out_path = build_dir / "verification.json"
    if out_path.exists():
        return None  # already verified — idempotent
    manifest = _read_manifest(build_dir)
    if manifest is None:
        return None
    valuation_iso = str(manifest.get("valuation_time", ""))
    if not valuation_iso:
        return None
    t0 = datetime.fromisoformat(valuation_iso)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=UTC)
    window_end = t0 + timedelta(hours=horizon_h)
    if window_end + timedelta(hours=grace_h) > now:
        log.info("verify.skip", reason="horizon_not_elapsed", build=build_dir.name)
        return None

    clusters = list(manifest.get("clusters", []))
    aoi_ids = sorted({str(c["aoi_id"]) for c in clusters})

    matched_by_cluster: dict[int, list[str]] = {}
    min_dist_by_cluster: dict[int, float] = {}
    lead_hours_by_event: dict[str, float] = {}
    for c in clusters:
        cid = int(c["cluster_id"])
        cell_ids = list(c.get("cell_ids", []))
        if not cell_ids:
            continue
        rows = await conn.fetch(_ZONE_MATCH_SQL, cell_ids, t0, window_end, radius_m)
        ids = [str(r["event_id"]) for r in rows]
        if ids:
            matched_by_cluster[cid] = ids
            min_dist_by_cluster[cid] = min(float(r["dist_m"]) for r in rows)
        for r in rows:
            lead_hours_by_event[str(r["event_id"])] = (
                r["event_time"] - t0
            ).total_seconds() / 3600.0

    aoi_rows = await conn.fetch(_AOI_EVENTS_SQL, aoi_ids, t0, window_end)
    aoi_event_ids = {str(r["event_id"]) for r in aoi_rows}

    outcome = summarize_build(
        build_id=build_dir.name,
        valuation_time=valuation_iso,
        horizon_h=horizon_h,
        shown_level=str(manifest.get("shown_level", "")),
        clusters=clusters,
        matched_by_cluster=matched_by_cluster,
        aoi_event_ids=aoi_event_ids,
        lead_hours_by_event=lead_hours_by_event,
        min_dist_by_cluster=min_dist_by_cluster,
        verified_at=now.isoformat(),
    )
    out_path.write_text(json.dumps(asdict(outcome), ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(
        "verify.build.done",
        build=build_dir.name,
        zones=len(outcome.zones),
        hits=sum(1 for z in outcome.zones if z.outcome == "hit"),
        misses=len(outcome.miss_event_ids),
        pod=round(outcome.pod, 3),
        far=round(outcome.far, 3),
    )
    return outcome


def _write_report(outcomes: list[BuildOutcome], *, out_dir: Path, now: datetime) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"verification_{now.date()}.md"
    lines = [
        "# Limen — verifica a posteriori delle zone segnalate (#17)",
        "",
        f"Generato: {now.isoformat()} · build verificati: **{len(outcomes)}**",
        "",
        "| build | zone | hit | falso allarme | miss | POD | FAR | lead medio (h) |",
        "|-------|------|-----|---------------|------|-----|-----|----------------|",
    ]
    for o in outcomes:
        hits = sum(1 for z in o.zones if z.outcome == "hit")
        fa = sum(1 for z in o.zones if z.outcome == "false_alarm")
        lead = f"{o.mean_lead_time_h:.1f}" if o.mean_lead_time_h is not None else "—"
        lines.append(
            f"| `{o.build_id}` | {len(o.zones)} | {hits} | {fa} | "
            f"{len(o.miss_event_ids)} | {o.pod:.2f} | {o.far:.2f} | {lead} |"
        )
    if not outcomes:
        lines.append("| _nessun build oltre l'orizzonte da verificare_ |||||||| ")
    lines.append("")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


async def run() -> int:
    """``limen verify`` — verify all archived builds past the horizon."""
    from limen.config.settings import Settings
    from limen.data.db import lifespan_pool
    from limen.data.migrate import run_migrations

    settings = Settings()
    cfg = settings.verify
    archive = Path(settings.report.html_output_dir) / "archive"
    now = datetime.now(UTC)

    if not archive.exists():
        log.info("verify.skip", reason="no archive", path=str(archive))
        return 0

    outcomes: list[BuildOutcome] = []
    async with lifespan_pool():
        await run_migrations()
        async with acquire() as conn:
            for build_dir in sorted(p for p in archive.iterdir() if p.is_dir()):
                res = await verify_build(
                    conn,
                    build_dir,
                    horizon_h=cfg.horizon_hours,
                    grace_h=cfg.grace_hours,
                    radius_m=cfg.match_radius_m,
                    now=now,
                )
                if res is not None:
                    outcomes.append(res)

    report = _write_report(outcomes, out_dir=Path("./reports"), now=now)
    log.info("verify.done", verified=len(outcomes), report=str(report))
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
