"""Static-feature bootstrap (one-shot, idempotent).

Populates ``cell_static_factors`` with values that the scoring engine
will combine into ``s_static`` in Phase 3. This pipeline is intentionally
*partial*: every dataset is optional and a missing source writes NULL +
logs ``static_bootstrap.skip`` rather than crashing the run.

Currently implemented (no external downloads required):

* ``iffi_density_500``  — IFFI feature density inside a 500 m buffer
  around each cell's centroid, computed with PostGIS.
* ``distance_to_iffi_m`` — distance from the cell centroid to the
  nearest IFFI feature.
* ``pai_class_norm``    — normalised PAI hazard class (max over polygons
  intersecting the cell), pulled from ``pai_hazard.hazard_class_norm``.

Marked as TODO for later prompts (when DEM/raster pipelines and CORINE
ingest land):

* ``slope_deg``, ``aspect_deg``, ``curvature`` — derived from the DTM via
  rasterio + numpy / scipy.
* ``elevation_m``       — mean DEM elevation per cell.
* ``landuse_code`` — CORINE dominant code per cell.
* ``lithology`` / ``litho_weight`` / ``dist_faults_m`` — ISPRA Carta
  Geologica vettoriale; ``dist_faults_m`` only with ``LIMEN_FAULTS_SHAPEFILE``.

``twi`` has no step (#466): it is a feature of the ML challenger, read as 0
when NULL, and computing it from the DTM waits for a measurement of its
signal (AUC on landslides and flooded cells) before it costs a bootstrap.
"""

from limen.integrations.static_bootstrap.orchestrator import bootstrap_static_for_aoi

__all__ = ["bootstrap_static_for_aoi"]
