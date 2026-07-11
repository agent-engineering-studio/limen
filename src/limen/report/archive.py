"""Output versionato immutabile del report + indice timeline + retention.

Ogni build va in report/archive/<build_id>/ e NON viene mai riscritto.
Solo report/index.html (redirect) e report/archive/index.json sono mutabili.
I manifest.json non vengono mai potati (dataset per il fact-checking).
"""

from __future__ import annotations

import json
from pathlib import Path

from limen.core.logging import get_logger

log = get_logger(__name__)

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
    """Scrive un build immutabile; aggiorna puntatore + indice. Ritorna la dir.

    Chiamare con un ``build_id`` esistente sovrascrive quel build (last-wins per
    lo stesso bucket temporale); l'immutabilità vale TRA build_id distinti, che è
    ciò che il caller basato su timestamp garantisce.
    """
    build_dir = root / "archive" / build_id
    (build_dir / "assets").mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text(html, encoding="utf-8")
    (build_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, data in assets.items():
        (build_dir / "assets" / name).write_bytes(data)

    (root / "index.html").write_text(_REDIRECT.format(build_id=build_id), encoding="utf-8")
    _update_index(root, build_id, manifest)
    return build_dir


def _update_index(root: Path, build_id: str, manifest: dict[str, object]) -> None:
    idx_path = root / "archive" / "index.json"
    builds: list[dict[str, object]] = []
    if idx_path.exists():
        try:
            builds = json.loads(idx_path.read_text(encoding="utf-8"))["builds"]
        except (json.JSONDecodeError, KeyError, OSError):
            log.warning("report.archive.index_reset", index=str(idx_path))
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
    to_prune = build_dirs[: len(build_dirs) - keep] if keep < len(build_dirs) else []
    for old in to_prune:
        html = old / "index.html"
        if html.exists():
            html.unlink()
        assets = old / "assets"
        if assets.exists():
            for f in assets.glob("*"):
                f.unlink()
            assets.rmdir()
