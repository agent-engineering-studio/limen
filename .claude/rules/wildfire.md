---
paths:
  - "src/limen/core/scoring/wildfire/**"
  - "src/limen/config/hazards/wildfire.yaml"
  - "src/limen/agents/executors/fwi_update*"
  - "src/limen/agents/executors/fire_check*"
  - "src/limen/integrations/effis/**"
  - "src/limen/integrations/firms/**"
  - "src/limen/data/repos/fwi_state*"
  - "src/limen/cli/**"
---

# Pericolo incendio, catena FWI, EFFIS

Testo completo degli invarianti di cui `CLAUDE.md` tiene solo la riga breve:
la regola e il perché (misure, incidenti, issue). Vincolanti quanto la tabella.

| Topic | Rule |
|-------|------|
| Wildfire: the weather gates the score | `score = fwi_norm × (base + fuel·f + slope·s)` — the terrain **modulates** the weather, never adds to it. A sum gave a conifer cell a weather-independent floor, so it read "Moderate" under a January downpour and the low classes were unreachable. `base` is why it is not a plain product: it is the danger a cell carries because fire arrives from outside it, so bare rock in extreme weather still scores. The three weights sum to 1, so a conifer cell on a saturated slope scores exactly its normalised FWI and the class cutoffs stay readable as EFFIS bands. The chain itself (Van Wagner 1987, the `fwi-chain` package on PyPI) is pure and verified against the published reference day to 1e-9. |
| The FWI chain is per weather node | The three moisture codes depend only on the weather, which Open-Meteo serves at ~9 km, so `fwi_state` is keyed by `(node_lon, node_lat, day)` — NUMERIC, because float equality in a PK opens a second chain on rounding noise. Keying it by cell would store the same six numbers ~500 times a day per region. Nodes come from `build_snapped_nodes` (a **global** lattice), never `build_rain_nodes` (bbox-anchored): a persisted chain's identity must not move when an AOI boundary is redrawn. The grid step is `fwi.node_spacing_deg` in `wildfire.yaml`, **not** an env knob: changing it starts fresh chains and restarts the spin-up. A stored state older than `fwi.max_gap_days` is discarded rather than carried — `chain_days` would otherwise keep climbing until `spinup` called a broken chain settled. Retention must never delete past days: the recursion walks through them. |
| EFFIS is MapServer, not GeoServer | `maps.effis.emergency.copernicus.eu/gwis` is a **MapServer** CGI, and every GeoServer habit fails differently: `/gwis/ows` hangs (use `/gwis`), a wrong `typeNames` closes the connection mid-response instead of 404ing, `CQL_FILTER` is silently ignored, and `bbox` + `filter` together kill the connection. The layer is `nrt.ba.poly` with `initialdate`/`area`; dates are filtered **client-side** after a bbox request, which is cheap because one AOI's whole history is a single response (Basilicata: 515 perimeters 2012-2026, 305 KB). A sync that returns zero is a client bug, not missing credentials — that mistake cost this project a year of an empty `fire_perimeters` and three issues blocked on an accreditation nobody needed. The request and parsing now live in the `effis-client` package (extracted from Limen, Apache-2.0, `agent-engineering-studio/effis-client`), perimeters and the official FWI WMS alike; the retry through `_http` and the neutral degradation stay here. |
| A hit rate without a base rate is unreadable | `backtest-wildfire` reports both, plus their ratio. A model that calls every summer day dangerous scores a perfect hit rate while discriminating nothing, and the base rate is what exposes it. Measure it over the **fire season only**, never the spin-up days: including them dropped Basilicata's 2025 base from 43 % to 35 % and inflated the discrimination from 1.82 to 2.27 for free. |
