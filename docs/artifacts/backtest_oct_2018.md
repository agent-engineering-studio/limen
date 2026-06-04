# Backtest — Southern-Italy storm, October 2018

> Sample artifact rendered by `limen backtest` against the V1 stack.
> Reproduce locally with the canonical window:

```bash
LIMEN_BACKTEST_AOI=it-puglia \
LIMEN_BACKTEST_START=2018-10-28T00:00:00+00:00 \
LIMEN_BACKTEST_END=2018-11-02T00:00:00+00:00 \
  uv run limen backtest
```

The runner writes `reports/backtest_it-puglia_2018-10-28_2018-11-02.md`
with the §2.5 metrics + PASS/FAIL annotations against the YAML
targets:

* **Hit rate** ≥ 70 %
* **FAR** ≤ 30 %
* **Mean lead time** ≥ 18 h

## Expected report skeleton

```
# Limen backtest report — AOI `it-puglia`

Window: **2018-10-28T00:00:00+00:00 → 2018-11-02T00:00:00+00:00**
Generated: <utc-iso>

- Cells scored per hour: <n>
- Truth events (IFFI in window): <k>
- Alert-level cell-hours: <m>
- Hits: <h>, false alarms: <f>, misses: <i>

## §2.5 metrics

- **Hit rate**: <pct> (target ≥ 70%) — PASS|FAIL
- **FAR**: <pct> (target ≤ 30%) — PASS|FAIL
- **Mean lead time**: <h> h (target ≥ 18 h) — PASS|FAIL
```

## Reproducibility

The replay is fully deterministic given:

* the same `regional_thresholds.yaml`,
* the same Open-Meteo ERA5 archive responses (cached in
  `app_cache` by `CachedOpenMeteoClient` so a second run is offline),
* the same `iffi_landslides.occurrence_date` truth set.

If you tweak weights in the YAML, regenerate this artifact and commit
both — they form the design audit trail for the V2 ML model.

## Sample numbers (V1 default weights, mocked Open-Meteo)

Below are the metrics produced by the integration test
`tests/integration/test_cli_runners.py::test_backtest_runs`, which
runs the same code path on the testcontainers Postgres with a
synthetic rainfall payload. Real-world ERA5 numbers will differ; this
is the smoke-test floor.

| Metric | Value | Target | Status |
|---|---|---|---|
| Hit rate | n/a (no IFFI rows in synthetic window) | ≥ 70% | n/a |
| FAR | 0.0 | ≤ 30% | PASS |
| Mean lead time | 0.0 h | ≥ 18 h | n/a |

For the real Oct-2018 numbers, ingest the IFFI Oct-Nov 2018 records
via `limen` (Phase 2 sync) and re-run the command above.
