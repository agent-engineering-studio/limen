"""GeoServer PostGIS as the authoritative source of ISPRA static data.

Reads the IFFI landslide inventory (historical landslides) and the PAI
hazard mosaic from the GeoServer-backed PostGIS (the mcp-geo-server stack)
and upserts them into the operational ``iffi_landslides`` / ``pai_hazard``
tables. Downstream, ``limen bootstrap-static`` computes the per-cell static
features unchanged — so GeoServer replaces the IdroGeo WFS ingest as the
source without touching the scoring path.

Read-only against GeoServer: if the DSN is unset or the source is
unreachable, the loader logs ``integration.degraded`` and returns 0 rather
than raising (writes into the operational DB still raise on failure).
"""

from __future__ import annotations

from limen.integrations.geoserver_source.loader import sync_geoserver_source_for_aoi

__all__ = ["sync_geoserver_source_for_aoi"]
