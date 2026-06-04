"""Self-contained parsers — Prompt-2 logic copied here.

This module deliberately duplicates the small set of geometry +
attribute helpers that live in ``limen.integrations.idrogeo.parsers``.
The duplication is intentional: ``geodata/`` is designed to be
extractable into a standalone repo with a single directory move, so
nothing here imports from ``limen.*``.

If ISPRA changes a field name, edit both copies; the integration
tests catch divergence (different parser → different row counts).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

# Canonical PAI hazard classes the importer recognises. UNKNOWN is a
# sentinel — unrecognised inputs land here so we never drop rows on
# upstream schema drift.
PAI_CLASSES: tuple[str, ...] = ("AA", "P1", "P2", "P3", "P4", "UNKNOWN")


def ensure_valid(geom: BaseGeometry) -> BaseGeometry:
    """Make a geometry valid in place (Shapely 2 contract)."""
    return geom if geom.is_valid else make_valid(geom)


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    s = str(value)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def normalise_pai_class(raw: Any) -> str:
    """Upper-case + strip; map empties to ``UNKNOWN``.

    The PAI mosaic uses the ``AA / P1 / P2 / P3 / P4`` ladder almost
    everywhere; the rare outlier (e.g. ``"Pn.d."``) survives as
    ``UNKNOWN`` so the row imports — the downstream exporter then
    filters by canonical class.
    """
    if raw is None:
        return "UNKNOWN"
    s = str(raw).strip().upper()
    if not s:
        return "UNKNOWN"
    return s if s in PAI_CLASSES else "UNKNOWN"


def parse_iffi_attributes(props: dict[str, Any]) -> dict[str, Any]:
    """Pick the IFFI fields Limen consumes + keep the raw props for audit.

    Field aliasing matches the existing Limen integration so the row
    shape is identical regardless of which ingest path filled it.
    """
    return {
        "iffi_id": str(props.get("iffi_id") or props.get("id_frana") or props.get("idfrana") or "")
        or None,
        "movement_type": props.get("movement")
        or props.get("movimento")
        or props.get("mov_principale"),
        "state": props.get("state") or props.get("stato"),
        "velocity_class": props.get("velocity_class") or props.get("classe_velocita"),
        "occurrence_date": parse_date(props.get("data_evento") or props.get("occurrence_date")),
        # IFFI ZIPs ship different geometry layers (line/poly/aree/dgpv)
        # whose distinction matters for the MCP `iffi_query` tool —
        # callers set this from the shapefile's own geometry type.
        "geom_type": props.get("geom_type"),
        "raw": dict(props),
    }


def parse_pai_attributes(props: dict[str, Any]) -> dict[str, Any]:
    hazard_class_raw = (
        props.get("hazard_class")
        or props.get("classe_pai")
        or props.get("pericolosita")
        or props.get("classe")
    )
    return {
        "pai_id": str(props.get("pai_id") or props.get("id_pai") or props.get("idpai") or "")
        or None,
        "hazard_class": normalise_pai_class(hazard_class_raw),
        "authority": props.get("authority")
        or props.get("autorita")
        or props.get("autorita_bacino"),
        "raw": dict(props),
    }


def shape_from_geometry(geom_field: Any) -> BaseGeometry | None:
    """Defensive ``shapely.shape`` — return None instead of raising."""
    if not geom_field:
        return None
    try:
        return ensure_valid(shape(geom_field))
    except (ValueError, TypeError):
        return None


__all__ = [
    "PAI_CLASSES",
    "ensure_valid",
    "normalise_pai_class",
    "parse_date",
    "parse_iffi_attributes",
    "parse_pai_attributes",
    "shape_from_geometry",
]
