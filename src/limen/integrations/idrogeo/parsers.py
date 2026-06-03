"""Feature parsers for ISPRA IdroGEO data.

ISPRA's WFS schema is *not* fully standardised across regions and layer
revisions: field names drift, missing values appear, geometry types
overlap between point/poly/line layers. Each parser is therefore
*defensive* — it tolerates missing fields, accepts multiple aliases,
and skips rather than crashes on broken input.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from limen.core.logging import get_logger
from limen.data.repos.iffi_repo import IFFILandslide
from limen.data.repos.pai_repo import PAIHazard

log = get_logger(__name__)


def _ensure_valid(geom: BaseGeometry) -> BaseGeometry:
    return geom if geom.is_valid else make_valid(geom)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    s = str(value)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def parse_iffi_feature(feat: dict[str, Any]) -> IFFILandslide | None:
    """Map one IFFI feature (GeoJSON) → :class:`IFFILandslide`.

    Field aliases (best-effort, matching ISPRA practice):

    * id: ``iffi_id`` / ``id_frana`` / ``idfrana`` / feature ``id``
    * movement_type: ``movement`` / ``movimento`` / ``mov_principale``
    * state: ``state`` / ``stato``
    * velocity_class: ``velocity_class`` / ``classe_velocita``
    * occurrence_date: ``data_evento`` / ``occurrence_date``
    """
    props = dict(feat.get("properties") or {})

    iffi_id = (
        props.get("iffi_id") or props.get("id_frana") or props.get("idfrana") or feat.get("id")
    )
    if not iffi_id:
        log.warning("iffi.skip", reason="no id")
        return None

    geom_field = feat.get("geometry")
    if not geom_field:
        log.warning("iffi.skip", reason="no geometry", iffi_id=iffi_id)
        return None
    try:
        geom = _ensure_valid(shape(geom_field))
    except (ValueError, TypeError) as e:
        log.warning("iffi.skip", reason=f"bad geometry: {e}", iffi_id=iffi_id)
        return None

    return IFFILandslide(
        id=str(iffi_id),
        movement_type=(
            props.get("movement") or props.get("movimento") or props.get("mov_principale")
        ),
        state=props.get("state") or props.get("stato"),
        velocity_class=props.get("velocity_class") or props.get("classe_velocita"),
        occurrence_date=_parse_date(props.get("data_evento") or props.get("occurrence_date")),
        geom=geom,
        attributes=props,
    )


def parse_pai_feature(feat: dict[str, Any]) -> PAIHazard | None:
    """Map one PAI hazard feature → :class:`PAIHazard`.

    PAI hazard classes are normally one of ``AA, P1, P2, P3, P4``. We
    upper-case and strip whitespace before lookup; unknown classes are
    accepted (so we don't lose rows) but ``hazard_class_norm`` becomes
    NULL for them.
    """
    props = dict(feat.get("properties") or {})
    pai_id = props.get("pai_id") or props.get("id_pai") or props.get("idpai") or feat.get("id")
    if not pai_id:
        log.warning("pai.skip", reason="no id")
        return None

    hazard_class = (
        props.get("hazard_class")
        or props.get("classe_pai")
        or props.get("pericolosita")
        or props.get("classe")
        or ""
    )
    hazard_class = str(hazard_class).strip().upper()

    geom_field = feat.get("geometry")
    if not geom_field:
        log.warning("pai.skip", reason="no geometry", pai_id=pai_id)
        return None
    try:
        geom = _ensure_valid(shape(geom_field))
    except (ValueError, TypeError) as e:
        log.warning("pai.skip", reason=f"bad geometry: {e}", pai_id=pai_id)
        return None

    # PAIHazard's geom field is declared MultiPolygon; pai_repo.upsert_many
    # performs the Polygon → MultiPolygon coercion (and skips non-polygon
    # geometries) so we forward the raw shapely geometry here.
    return PAIHazard(
        id=str(pai_id),
        hazard_class=hazard_class or "UNKNOWN",
        authority=props.get("authority") or props.get("autorita") or props.get("autorita_bacino"),
        geom=geom,
        attributes=props,
    )
