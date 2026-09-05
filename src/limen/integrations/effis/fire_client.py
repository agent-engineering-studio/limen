"""EFFIS burnt-area perimeters client.

EFFIS exposes burnt-area features through its rapid-damage-assessment
WMS/WFS endpoints. The programmatic access this client targets is the
WFS GetFeature on
``https://maps.effis.emergency.copernicus.eu/gwis``; full annual
perimeter shapefiles and dNBR rasters often require a manual EFFIS data
request.

Two fetch paths are supported:

* :meth:`EffisHttpClient.fetch_perimeters` — WFS GetFeature, GeoJSON
  output. Default for the hourly sync.
* :meth:`EffisHttpClient.fetch_perimeters_bulk` — bulk Shapefile ZIP
  fallback. Use when the WFS is unreliable or for a long
  retro-window: a single ZIP download + local filtering by date /
  bbox replaces dozens of WFS calls.

Returns:
    Raw GeoJSON features (one feature = one burnt-area polygon). The
    sync job converts them to :class:`FirePerimeter`.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from typing import TYPE_CHECKING, Any

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

if TYPE_CHECKING:
    from collections.abc import Iterable

log = get_logger(__name__)

# Default WFS endpoint and typeName. Override at construction time if
# Copernicus moves endpoints.
#
# The endpoint is **MapServer**, not GeoServer, and that shapes every choice
# below. Verified against the live service:
#
# * the base path is ``/gwis``, not ``/gwis/ows`` — the latter hangs;
# * the layer is ``nrt.ba.poly``. ``effis:ba.fires`` does not exist, and a
#   request for it makes MapServer close the connection mid-response, which
#   surfaces as a transport error rather than a 404;
# * ``CQL_FILTER`` is a GeoServer vendor parameter. MapServer ignores it, so
#   a date range expressed that way silently filtered nothing;
# * ``bbox`` and ``filter`` are mutually exclusive in WFS (and combining them
#   here kills the connection), so the bbox goes on the wire and the dates are
#   applied locally. Cheap in practice: one AOI's whole history is a single
#   response — Basilicata is 515 perimeters across 2012-2026, 305 KB.
DEFAULT_WFS_URL = "https://maps.effis.emergency.copernicus.eu/gwis"
DEFAULT_TYPENAME = "nrt.ba.poly"

#: Server-side cap. Above the largest per-AOI history we measured, so the
#: local date filter never sees a truncated set.
DEFAULT_MAX_FEATURES = 5000

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


def _feature_date(feat: dict[str, Any]) -> date | None:
    """The day a fire started, from whichever field this layer carries."""
    props = feat.get("properties") or {}
    for key in ("initialdate", "firedate", "FIREDATE", "fire_date"):
        raw = props.get(key)
        if raw:
            try:
                return date.fromisoformat(str(raw)[:10])
            except ValueError:
                return None
    return None


def _within(feat: dict[str, Any], start: date, end: date) -> bool:
    """Keep a feature whose start date falls in the window.

    A feature with no readable date is **kept**: the sync stores it with a
    NULL date, which a backtest ignores, and dropping it here would lose a
    perimeter that is still real.
    """
    when = _feature_date(feat)
    return when is None or start <= when <= end


class EffisHttpClient:
    """Concrete :class:`EffisClient` Protocol implementation."""

    def __init__(
        self,
        *,
        wfs_url: str = DEFAULT_WFS_URL,
        typename: str = DEFAULT_TYPENAME,
        http_client: httpx.AsyncClient | None = None,
        max_features: int = DEFAULT_MAX_FEATURES,
    ) -> None:
        self._wfs_url = wfs_url
        self._typename = typename
        self._http = http_client
        self._max_features = max_features

    async def _client(self) -> httpx.AsyncClient:
        return self._http if self._http is not None else await SharedHttpClient.get()

    async def fetch_perimeters(
        self,
        *,
        bbox: tuple[float, float, float, float],
        start: date,
        end: date,
    ) -> Iterable[dict[str, Any]]:
        """Return burnt-area features intersecting ``bbox`` for ``[start, end]``.

        On terminal failure, returns ``[]`` and logs ``integration.degraded``.
        """
        params: dict[str, Any] = {
            "service": "WFS",
            "version": "1.1.0",
            "request": "GetFeature",
            # Lowercase keys: MapServer's WFS 1.1.0 does not accept the
            # camelCase spellings GeoServer tolerates.
            "typename": self._typename,
            "outputformat": "geojson",
            "srsname": "EPSG:4326",
            "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "maxfeatures": str(self._max_features),
        }
        log.info(
            "effis.perimeters.fetch",
            bbox=bbox,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        try:
            resp = await fetch_with_retry(
                "GET", self._wfs_url, client=await self._client(), params=params
            )
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label="effis.perimeters",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return []

        if resp.status_code == 204 or not resp.content:
            return []

        try:
            payload = resp.json()
        except ValueError:
            log.warning("effis.perimeters.bad_payload", status=resp.status_code)
            return []
        features = list(payload.get("features") or [])
        if len(features) >= self._max_features:
            # The local date filter below would then be working on a truncated
            # set, and the gap would look like "no fires that summer".
            log.warning(
                "effis.perimeters.truncated",
                count=len(features),
                max_features=self._max_features,
            )
        in_window = [f for f in features if _within(f, start, end)]
        log.info(
            "effis.perimeters.fetched",
            fetched=len(features),
            in_window=len(in_window),
            start=start.isoformat(),
            end=end.isoformat(),
        )
        return in_window

    async def fetch_perimeters_bulk(
        self,
        *,
        bulk_url: str,
        bbox: tuple[float, float, float, float] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Fallback path: download an EFFIS bulk shapefile + filter locally.

        Use when the WFS is flaky, or for a long retro-window where
        dozens of WFS calls would be heavier than one ZIP fetch. The
        returned features have the same GeoJSON shape as
        :meth:`fetch_perimeters` so the sync job's parser is unchanged.

        ``bbox`` filters by spatial intersection (EPSG:4326);
        ``start`` / ``end`` filter on ``firedate`` (inclusive). Both
        filters are optional — pass ``None`` to keep the whole archive.

        Degrades to ``[]`` on download / parse failure with a structured
        log; never raises so callers can safely fall through to the WFS
        path.
        """
        log.info("effis.perimeters.bulk_fetch", url=bulk_url)
        try:
            resp = await fetch_with_retry("GET", bulk_url, client=await self._client())
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label="effis.perimeters.bulk",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return []
        if not resp.content:
            return []

        try:
            features = _features_from_shapefile_zip(resp.content)
        except Exception as exc:  # bulk archive corrupted / wrong layout
            log.warning(
                "effis.perimeters.bulk_bad_archive",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return []

        filtered = _filter_features(features, bbox=bbox, start=start, end=end)
        log.info(
            "effis.perimeters.bulk_fetched",
            count_total=len(features),
            count_after_filter=len(filtered),
        )
        return filtered

    async def fetch_dnbr(self, *, perimeter_id: str) -> bytes | None:
        """Best-effort dNBR raster download for a single perimeter.

        EFFIS dNBR products typically require the manual data-request
        workflow (https://forest-fire.emergency.copernicus.eu/applications/data-and-services).
        This client returns ``None`` and logs a TODO so the workflow
        proceeds without dNBR; a future prompt can plug a programmatic
        endpoint here when Copernicus publishes one.
        """
        log.info(
            "effis.dnbr.not_implemented",
            perimeter_id=perimeter_id,
            note=(
                "EFFIS dNBR rasters require the manual data-request workflow; "
                "implement once Copernicus exposes a programmatic endpoint."
            ),
        )
        return None


# ---------------------------------------------------------------------------
# Bulk-shapefile helpers — used by :meth:`fetch_perimeters_bulk`.
# ---------------------------------------------------------------------------
def _features_from_shapefile_zip(payload: bytes) -> list[dict[str, Any]]:
    """Unpack a ZIPped shapefile and return its features as GeoJSON dicts.

    Uses pyogrio for the read so we don't haul GeoPandas into the
    hot path. The function is sync — caller's already inside an
    async wrapper.
    """
    import shutil
    import tempfile
    from pathlib import Path

    from pyogrio import read_dataframe

    with tempfile.TemporaryDirectory(prefix="effis-bulk-") as workdir:
        wd = Path(workdir)
        # Safe extraction: refuse path-traversal entries.
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            base = wd.resolve()
            for info in zf.infolist():
                if not info.filename or info.filename.endswith("/"):
                    continue
                target = (wd / info.filename).resolve()
                try:
                    target.relative_to(base)
                except ValueError as exc:
                    raise ValueError(
                        f"refusing path-traversal entry in EFFIS bulk: {info.filename!r}"
                    ) from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

        shapefiles = sorted(wd.rglob("*.shp"))
        if not shapefiles:
            raise ValueError("EFFIS bulk archive contains no .shp file")
        gdf = read_dataframe(shapefiles[0])
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    import json

    return [json.loads(gdf.iloc[i : i + 1].to_json())["features"][0] for i in range(len(gdf))]


def _filter_features(
    features: list[dict[str, Any]],
    *,
    bbox: tuple[float, float, float, float] | None,
    start: date | None,
    end: date | None,
) -> list[dict[str, Any]]:
    """Local spatial + temporal filter used by the bulk fallback."""
    from datetime import datetime as _dt

    from shapely.geometry import box, shape

    bbox_geom = box(*bbox) if bbox is not None else None
    out: list[dict[str, Any]] = []
    for feat in features:
        props = feat.get("properties") or {}
        firedate_raw = props.get("firedate") or props.get("date")
        if start is not None or end is not None:
            firedate = _parse_firedate(firedate_raw)
            if firedate is None:
                continue
            if start is not None and firedate < start:
                continue
            if end is not None and firedate > end:
                continue
        if bbox_geom is not None:
            try:
                geom = shape(feat.get("geometry") or {})
            except (ValueError, TypeError):
                continue
            if not geom.intersects(bbox_geom):
                continue
        out.append(feat)
        _ = _dt  # silence unused-import — kept for forward compat
    return out


def _parse_firedate(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None
