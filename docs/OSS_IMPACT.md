# OSS impact and reuse

Limen is designed as open-source civic and scientific infrastructure for landslide-risk monitoring. It combines public geospatial and environmental datasets with interpretable scoring, PostGIS, APIs, maps and notification workflows.

## Why it matters

Landslide-risk information is often distributed across heterogeneous datasets, portals and formats. Limen aims to make that information easier to operationalize by combining:

- a 1 km² grid model over Italian territory;
- public hazard, morphology, rainfall, soil-moisture, seismic and fire-history signals;
- interpretable multi-factor scoring;
- PostGIS-native storage and vector-tile serving;
- API and frontend map access;
- MCP tools for agentic geospatial workflows;
- deterministic reports and alerts that show why risk changed.

## Who benefits

- Researchers who need reproducible geospatial risk workflows.
- Civic-tech groups working with environmental and territorial data.
- Public administrators and technical offices evaluating monitoring prototypes.
- Developers building PostGIS, map and MCP-based geospatial tools.
- Journalists and local communities exploring environmental-risk information.

## Reusable components

Limen is not only an application. Its most reusable OSS parts are:

- PostGIS grid and AOI modelling patterns;
- geospatial ingestion adapters;
- interpretable scoring configuration and thresholds;
- risk explanation and cell-breakdown APIs;
- vector-tile and MapLibre frontend patterns;
- notification and alert-deduplication workflows;
- MCP tools for risk summaries and operational queries.

## Responsible use

Limen is a monitoring and decision-support framework, not an official emergency-warning system unless validated and adopted by an authorized institution. Public communication should keep uncertainty visible and separate official-source data from derived/modelled indicators.

## Claude/AI relevance

Claude can help maintain the project by improving documentation, writing tests, reviewing scoring changes, checking runbooks and making the codebase easier for external contributors. AI-generated briefing text should remain grounded in deterministic model outputs and public data sources.

## Adoption goals

The next OSS goal is to make Limen easier to evaluate and reuse by external contributors. Useful indicators include:

- external issues and pull requests;
- reproducible setup by someone outside the maintainer team;
- documented reuse of geospatial modules or MCP tools;
- public validation reports and demo datasets;
- community contributions to datasets, docs, scoring tests or frontend map UX.

## Suggested Claude for OSS positioning

Limen should be positioned as an early-stage but serious open-source geospatial monitoring framework. It may not yet meet numerical thresholds such as many dependents or external contributors, but it has clear civic/scientific value, public-data grounding, interpretable scoring and reusable infrastructure for geospatial AI workflows.
