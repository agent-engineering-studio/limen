"""Orchestratore del report: dati -> cluster -> snapshot -> HTML -> archivio.

Idempotente: se l'ultimo build in archivio ha la stessa firma degli assessment
correnti, salta tutto (log report.skip). Nessun richiamo LLM (usa report_it
già persistito). Degrada in modo neutro: uno snapshot fallito non blocca il
build (render_cluster_png non solleva mai).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _canonical(obj: Any) -> Any:
    """Rende ``obj`` order-independent: liste ordinate per il loro JSON canonico."""
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in obj.items()}
    if isinstance(obj, list):
        items = [_canonical(v) for v in obj]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    return obj


def assessment_signature(payload: dict[str, object]) -> str:
    """SHA-256 su canonical-JSON, order-independent nelle liste -> firma stabile."""
    canonical = json.dumps(_canonical(payload), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_id_for(valuation_time_iso: str) -> str:
    dt = datetime.fromisoformat(valuation_time_iso)
    return dt.strftime("%Y-%m-%dT%H%MZ")


async def _aoi_ids() -> list[str]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT id FROM aoi ORDER BY id")
    return [str(r["id"]) for r in rows]


async def _latest_valuation(aoi_ids: list[str]) -> tuple[str, str]:
    """(valuation_time_iso, pipeline_version) dell'assessment più recente, o ("", "")."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ra.computed_at AS ts, ra.pipeline_version AS pv
            FROM risk_assessments ra JOIN grid_cells g ON g.id = ra.cell_id
            WHERE g.aoi_id = ANY($1::text[])
            ORDER BY ra.computed_at DESC
            LIMIT 1
            """,
            aoi_ids,
        )
    if row is None or row["ts"] is None:
        return ("", "")
    return (row["ts"].isoformat(), str(row["pv"]))


def _last_signature(root: Path) -> str | None:
    idx = root / "archive" / "index.json"
    if not idx.exists():
        return None
    # Un index.json malformato (JSON invalido O forma inattesa) non deve mai
    # bloccare i build futuri: qualunque errore ⇒ "nessun build precedente".
    try:
        builds = json.loads(idx.read_text(encoding="utf-8"))["builds"]
        sig = builds[-1]["assessment_sha256"]
    except (json.JSONDecodeError, OSError, AttributeError, TypeError, KeyError, IndexError):
        return None
    return str(sig) if sig is not None else None


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
        components=[
            ("Versante", d.s, "#8c6d31"),
            ("Pioggia", d.m, "#1f77b4"),
            ("Sisma", d.e, "#9467bd"),
            ("Incendi", d.f, "#d62728"),
            ("Idraulica", d.h, "#17becf"),
        ],
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
    all_clusters.sort(key=lambda c: (-c.max_score, c.cell_ids[0]))

    valuation_iso, pipeline_version = await _latest_valuation(aoi_ids)
    if not valuation_iso:
        log.info("report.skip", reason="no assessment")
        return None

    from limen.mcp.tools import national_report

    national = await national_report()

    # round(...,6): stessa scienza numerica non deve produrre firme diverse per
    # jitter di rappresentazione float (0.7000000001 vs 0.7).
    signature = assessment_signature(
        {
            "valuation_time": valuation_iso,
            "pipeline_version": pipeline_version,
            # report_it è escluso: contiene un timestamp di generazione (now())
            # che cambia a ogni chiamata e forzerebbe un rebuild continuo.
            # I totali nazionali (conteggi) sono la parte stabile che guida il testo.
            "national_totals": national.get("totals", {}),
            "clusters": [
                {
                    "cell_ids": c.cell_ids,
                    "max_score": round(c.max_score, 6),
                    "level": c.dominant.level,
                    "components": [
                        round(x, 6)
                        for x in (
                            c.dominant.s,
                            c.dominant.m,
                            c.dominant.e,
                            c.dominant.f,
                            c.dominant.h,
                        )
                    ],
                }
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
    # Un build_id riusato potrebbe avere asset orfani di un run precedente
    # interrotto: ripulisci prima di riscrivere, così la dir parte pulita.
    shutil.rmtree(build_dir, ignore_errors=True)
    cluster_views: list[ClusterView] = []
    manifest_clusters: list[dict[str, object]] = []
    for idx, c in enumerate(capped):
        colored = [(r.geom_json, color_for(RiskLevel(r.level))) for r in c.rows]
        png_path = build_dir / "assets" / f"cluster-{idx}.png"
        is_png = await render_cluster_png(
            out_path=png_path,
            bbox=c.bbox,
            colored_cells=colored,
            basemap_url_template=cfg.html_basemap_url_template,
            attribution=cfg.html_basemap_attribution,
        )
        ext = "png" if is_png else "svg"
        cluster_views.append(_cluster_to_view(c, f"assets/cluster-{idx}.{ext}"))
        manifest_clusters.append(
            {
                "cluster_id": c.cluster_id,
                "aoi_id": c.aoi_id,
                "cell_ids": c.cell_ids,
                "max_score": c.max_score,
                "level": c.dominant.level,
            }
        )

    view = ReportView(
        title="Limen — Zone a maggior rischio frana",
        valuation_time=valuation_iso,
        pipeline_version=pipeline_version,
        national_summary=str(national.get("report_it", "")),
        clusters=cluster_views,
    )
    html = render_html(view)
    manifest: dict[str, object] = {
        "valuation_time": valuation_iso,
        "pipeline_version": pipeline_version,
        "assessment_sha256": signature,
        "clusters": manifest_clusters,
    }
    # render_cluster_png ha già scritto gli asset in build_dir/assets/;
    # write_build scrive HTML+manifest e aggiorna puntatore/indice.
    result = write_build(root, build_id=build_id, html=html, assets={}, manifest=manifest)
    prune_archive(root, keep=cfg.html_archive_keep)
    log.info("report.built", build_id=build_id, clusters=len(cluster_views))
    return result
