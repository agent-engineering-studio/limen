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
from limen.report.clustering import Cluster, anomaly_cutoff, load_clusters
from limen.report.geojson import coord_label, zone_center, zone_feature_collection_json
from limen.report.palette import color_for, label_for
from limen.report.reasons import plain_summary, verdict
from limen.report.render import ClusterView, ReportView, render_html

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


_LEVELS_DESC = [RiskLevel.VeryHigh, RiskLevel.High, RiskLevel.Moderate, RiskLevel.Low]


def _threshold_candidates(alert_level: RiskLevel) -> list[RiskLevel]:
    """Alert threshold first, then progressively lower down to Low.

    The report must ALWAYS surface the *relatively* most-at-risk zones, even
    when nothing crosses the alert threshold. We try the configured level, and
    if it yields no zone we step down (High -> Moderate -> Low) to the first
    level that has zones — flagged as informational, never an alarm.
    """
    try:
        start = _LEVELS_DESC.index(alert_level)
    except ValueError:
        start = _LEVELS_DESC.index(RiskLevel.High)
    return _LEVELS_DESC[start:]


def _zones_notice(
    *, alert_level: RiskLevel, shown_level: RiskLevel, has_clusters: bool, diffuse_cells: int = 0
) -> str | None:
    """Italian banner shown when the report displays below-alert zones (or none)."""
    if not has_clusters:
        if diffuse_cells > 0:
            return (
                f"Rischio diffuso su {diffuse_cells} celle senza hotspot netti che "
                f"spicchino sullo sfondo regionale: quadro puramente informativo, "
                f"nessun allarme attivo."
            )
        return (
            "Nessuna zona a rischio rilevata: tutte le celle sono sotto la soglia "
            "minima. Quadro puramente informativo, nessun allarme attivo."
        )
    base: str | None = None
    if shown_level != alert_level:
        base = (
            f"Nessuna zona sopra la soglia di allerta ({label_for(alert_level)}). "
            f"Sono mostrate le aree relativamente più a rischio "
            f"(livello {label_for(shown_level)}) a scopo informativo: "
            f"nessun allarme attivo."
        )
    if diffuse_cells > 0:
        extra = (
            f"Sono evidenziati solo gli hotspot che spiccano sullo sfondo regionale; "
            f"altre {diffuse_cells} celle a rischio diffuso non sono elencate "
            f"singolarmente."
        )
        return f"{base} {extra}" if base else extra
    return base


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


def _cluster_to_view(c: Cluster, idx: int) -> ClusterView:
    d = c.dominant
    level = RiskLevel(d.level)
    v = verdict(level)
    lat, lon = zone_center(c)
    return ClusterView(
        cluster_id=c.cluster_id,
        aoi_id=c.aoi_id,
        level=level,
        level_label=label_for(level),
        level_color=color_for(level),
        max_score=c.max_score,
        n_cells=len(c.cell_ids),
        map_id=f"zone-{idx}",
        geojson=zone_feature_collection_json(c),
        center_lat=lat,
        center_lon=lon,
        coord_label=coord_label(lat, lon),
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

    # Try the alert threshold first; if no zone crosses it, step down so the
    # report still shows the relatively most-at-risk areas (informational).
    alert_level = cfg.html_min_level
    shown_level = alert_level
    per_aoi: dict[str, list[Cluster]] = {}
    for level in _threshold_candidates(alert_level):
        per_aoi = {}
        for aoi_id in aoi_ids:
            cs = await load_clusters(aoi_id, eps_deg=cfg.html_cluster_eps_deg, min_level=level)
            if cs:
                per_aoi[aoi_id] = cs
        if per_aoi:
            shown_level = level
            break

    # Salienza: per gli AOI con troppe celle a rischio (fallback a livello basso
    # ⇒ macchia diffusa), evidenzia solo le celle che spiccano sullo sfondo e
    # riporta il conteggio della coda lunga invece di elencare l'intera regione.
    all_clusters: list[Cluster] = []
    diffuse_cells = 0
    for aoi_id, clusters in per_aoi.items():
        cell_count = sum(len(c.cell_ids) for c in clusters)
        if cell_count <= cfg.html_salience_volume_trigger:
            all_clusters.extend(clusters)
            continue
        scores = [r.score for c in clusters for r in c.rows]
        floor = anomaly_cutoff(
            scores,
            reference_pct=cfg.html_salience_reference_pct,
            margin=cfg.html_salience_min_anomaly,
        )
        hotspots = await load_clusters(
            aoi_id, eps_deg=cfg.html_cluster_eps_deg, min_level=shown_level, score_floor=floor
        )
        kept = sum(len(c.cell_ids) for c in hotspots)
        diffuse_cells += cell_count - kept
        all_clusters.extend(hotspots)
        log.info(
            "report.salience",
            aoi_id=aoi_id,
            total_cells=cell_count,
            kept_cells=kept,
            diffuse_cells=cell_count - kept,
            floor=round(floor, 4),
        )

    all_clusters.sort(key=lambda c: (-c.max_score, c.cell_ids[0]))
    below_alert = bool(all_clusters) and shown_level != alert_level
    notice = _zones_notice(
        alert_level=alert_level,
        shown_level=shown_level,
        has_clusters=bool(all_clusters),
        diffuse_cells=diffuse_cells,
    )
    if below_alert:
        log.info("report.below_alert", alert=alert_level.value, shown=shown_level.value)

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
            "shown_level": shown_level.value,
            "diffuse_cells": diffuse_cells,
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
    cluster_views = [_cluster_to_view(c, idx) for idx, c in enumerate(capped)]
    manifest_clusters = [
        {
            "cluster_id": c.cluster_id,
            "aoi_id": c.aoi_id,
            "cell_ids": c.cell_ids,
            "max_score": c.max_score,
            "level": c.dominant.level,
            "center": list(zone_center(c)),  # [lat, lon]
        }
        for c in capped
    ]

    view = ReportView(
        title="Limen — Zone a maggior rischio frana",
        valuation_time=valuation_iso,
        pipeline_version=pipeline_version,
        national_summary=str(national.get("report_it", "")),
        basemap_url=cfg.html_basemap_url_template,
        basemap_attribution=cfg.html_basemap_attribution,
        clusters=cluster_views,
        notice=notice,
    )
    html = render_html(view)
    manifest: dict[str, object] = {
        "valuation_time": valuation_iso,
        "pipeline_version": pipeline_version,
        "assessment_sha256": signature,
        "shown_level": shown_level.value,
        "diffuse_cells": diffuse_cells,
        "clusters": manifest_clusters,
    }
    # Report interattivo: nessun asset raster da scrivere, le celle sono GeoJSON
    # inline; write_build scrive HTML+manifest e aggiorna puntatore/indice.
    result = write_build(root, build_id=build_id, html=html, assets={}, manifest=manifest)
    prune_archive(root, keep=cfg.html_archive_keep)
    log.info(
        "report.built",
        build_id=build_id,
        clusters=len(cluster_views),
        shown_level=shown_level.value,
    )
    return result
