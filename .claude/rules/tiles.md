---
paths:
  - "src/limen/data/migrations/**"
  - "src/limen/data/repos/**"
  - "src/limen/api/endpoints/**"
  - "src/limen/agents/executors/persist_result*"
  - "frontend/src/**"
---

# Viste, tile e rollup per comune

Testo completo degli invarianti di cui `CLAUDE.md` tiene solo la riga breve:
la regola e il perché (misure, incidenti, issue). Vincolanti quanto la tabella.

| Topic | Rule |
|-------|------|
| Tile pipeline | `mv_latest_risk` is a **plain view** since migration 048 (#125), despite the `mv_` prefix: `grid_cells` CROSS JOIN the enabled rows of `hazards`, LEFT JOIN `latest_risk` — one row per **(cell, hazard)**, upserted by PersistResult with the rows it writes — so the map shows a score the moment it is persisted, with nothing to refresh. The materialised one is `mv_comune_risk` (the per-comune rollup). **Always refresh it via `refresh_mv_latest_risk()`** (PersistResult executor calls it; the name stayed for its callers, it debounces to one run per 5 min and now refreshes only `mv_comune_risk`). Never `REFRESH MATERIALIZED VIEW mv_comune_risk` directly. |
| Views pin the default hazard | `mv_latest_risk` (a plain view over `latest_risk`) is one row per cell **per hazard**, so every consumer that counts cells filters on `hazard_type`. `v_risk_tiles` and `v_region_tiles` are pinned to `landslide` (`mv_comune_risk` is not: one row per comune and hazard since migration 051); the multi-hazard tile surface is `risk_at(z,x,y,hours_ago,hazard)`, which pg_tileserv serves with the parameter in the query string. The future has its own surface, `forecast_at(z,x,y,p_horizon,p_hazard)` (migration 060), reading `latest_forecast`: only cells ≥ Moderate, `p_hazard` NULL = worst of the forecast hazards, and **PL/pgSQL with `EXECUTE`, geometry carried through the window** — the SQL version with a second join to `cells` measured 98 s per z7 tile. A hazard whose nightly run did not happen has no future to choose: the timeline disables it instead of drawing an empty map that reads as calm. (Migration 060's header says flood is forecast only per comune: wrong — flood has per-cell rows like the others; it is immutable, so the correction lives here.) Changing horizon swaps the source with `setTiles` and does **not** rebuild the map. The SPA map uses the view for the default hazard and the function for any other — deliberately two paths, because switching the working default onto the function buys only symmetry. `NationalStrip` and the comuni list (`ComuniBoard`, with its `ComuneTrend` chart) follow the selector: a chosen hazard sets the threshold and the order of `/api/comuni?hazard=` and draws only that hazard's line, with its own class cutoffs; «Tutti i pericoli» ranks on the combined attention. |
