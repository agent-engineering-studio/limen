# Roadmap

This roadmap focuses on making Limen more useful, reproducible and welcoming as an open-source landslide-risk monitoring framework.

## Near term

- Improve onboarding docs for local Docker, Neon/dev and self-hosted deployment.
- Add more `good first issue` tasks for docs, tests, data adapters and frontend map improvements.
- Document each public data source with license, cadence, spatial resolution and ingestion assumptions.
- Add reproducible examples for one small AOI and one regional AOI.
- Expand tests around scoring thresholds, regional configuration and alert deduplication.

## OSS readiness

- Keep contribution, security, issue and PR templates up to date.
- Document architecture invariants and scoring assumptions in reviewer-friendly language.
- Track external contributions and credit contributors in release notes.
- Keep labels consistent: `good first issue`, `help wanted`, `documentation`, `geospatial`, `backend`, `frontend`, `data-source`, `scoring`, `security`.

## Scientific and operational reliability

- Publish validation notebooks/reports for reproducible backtests.
- Make uncertainty and limitations visible in API responses and UI copy.
- Add more explainability examples for individual cells and AOIs.
- Separate official-source data from derived/modelled indicators in the UI and docs.
- Strengthen monitoring around stale data, ingestion failures and drift.

## Reusable components

Potential reusable packages or extractable modules:

- geospatial ingestion helpers for Italian public hazard datasets;
- interpretable multi-factor scoring primitives;
- PostGIS grid and vector-tile utilities;
- alert deduplication and notification adapters;
- MCP tools for geospatial risk summaries.

## Long term

- Dynamic/forecast flood component (post-V2): combine forecast rainfall with the
  static ISPRA hazard class into a `flood_forecast` factor feeding the reserved
  `hydrology` weight — deterministic first, pure scoring, opt-in feed. Design
  recorded in issue #8; 2D hydraulic modelling stays out of scope.
- More regional validation cases.
- Cleaner package boundaries for data ingestion and scoring.
- Public demo datasets suitable for contributors without large downloads.
- Contributor-friendly benchmarks for speed, accuracy and false-alarm tradeoffs.
- Documentation for municipalities, researchers and civic-tech groups.
