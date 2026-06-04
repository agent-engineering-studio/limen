"""``limen-geodata`` — Geo-Data Service for ISPRA national datasets.

Implements project doc §3.3.4-ter. Three responsibilities:

1. **Init** — download from the official IdroGEO open-data URLs at
   first run / refresh, into the service's dedicated PostGIS volume.
   The Docker image carries no dataset bytes.
2. **Exports** — produce per-cell static features for Limen's
   operational DB (so Neon stays light) + PMTiles for the public map.
3. **MCP server** ``ispra-geo`` — read-only tools for agents
   (``hazard_at`` / ``iffi_query`` / ``pai_summary`` / ``dataset_status``)
   plus an admin-token-guarded ``refresh``.

The package is intentionally self-contained — nothing here imports
from ``limen.*``. The Prompt-2 parsers
(``make_valid`` / EPSG:4326 / PAI class mapping / IFFI ``geom_type``)
are duplicated in :mod:`geodata.parsers` so the folder can be
extracted into a standalone repo with a one-line directory move.
"""

__version__ = "0.1.0"

from geodata.manifest import (
    DatasetFormat,
    DatasetManifest,
    DatasetSpec,
    load_manifest,
)

__all__ = [
    "DatasetFormat",
    "DatasetManifest",
    "DatasetSpec",
    "__version__",
    "load_manifest",
]
