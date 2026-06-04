# Operations runbook

Operator-facing reference for the running V1 stack. Pair with
[`deployment.md`](./deployment.md) for the install path and
[`architecture.md`](./architecture.md) for the system shape.

## Normal-day cycle

| What | When | Owner |
|---|---|---|
| Hourly monitoring workflow | APScheduler in-process every `SCHEDULER__HOURLY_MONITORING_MINUTES` (default 60) | API container |
| ISPRA IdroGEO sync | APScheduler weekly cron (Mon 03:15 UTC) | API container |
| Cache cleanup | APScheduler every `SCHEDULER__CACHE_CLEANUP_INTERVAL_SECONDS` (default 300) when `SCHEDULER__CACHE_CLEANUP=apscheduler` | API container |
| `mv_latest_risk` refresh | Tail of every `PersistResultExecutor` call | Workflow |

## Health probes

* **Liveness** — `GET /health` returns 200 with `pool` and `cache`
  booleans. Container orchestrator should restart on 5+ consecutive
  failures.
* **Readiness** — `GET /ready` returns 503 until the lifespan finishes
  bootstrapping. Use this as the load-balancer health check; the
  `infra/docker/Dockerfile.api` `HEALTHCHECK` already targets it.

## Common operator commands

```bash
# One-shot workflow for one AOI (uses configured channels by env)
LIMEN_MONITOR_AOI=it-puglia uv run limen monitor-once

# Recompute s_static + per-AOI norm stats, run the §2.5 S↔ISPRA gate
uv run limen calibrate

# Replay any window — writes reports/backtest_<aoi>_<start>_<end>.md
LIMEN_BACKTEST_AOI=it-puglia \
LIMEN_BACKTEST_START=2018-10-28T00:00:00+00:00 \
LIMEN_BACKTEST_END=2018-11-02T00:00:00+00:00 \
  uv run limen backtest

# Trigger an alert pipeline test (high-level cell synthesised below)
docker compose -f infra/docker/docker-compose.demo.yml exec api \
  python -c "import asyncio; from limen.cli.monitor_once import run; asyncio.run(run())"
```

## Backups

PostGIS holds the source of truth. The ObjectStore only holds raster
bytes referenced by `raster_refs` — the DB has the checksums so a
re-pull is verifiable.

### Logical dump (small AOI / dev)

```bash
docker compose -f infra/docker/docker-compose.demo.yml exec postgres \
  pg_dump -U limen -d limen --format=custom --no-owner \
          --file=/var/lib/postgresql/data/limen.dump
```

### Physical base backup (prod, Aruba VPS)

Configure `wal_level=replica` and use `pg_basebackup` to an external
volume. Document the restore procedure below in your runbook.

### Restore

```bash
docker compose -f infra/docker/docker-compose.demo.yml exec postgres \
  pg_restore -U limen -d limen --clean --if-exists /var/lib/postgresql/data/limen.dump
```

After a restore, **re-refresh the matview**:

```sql
SELECT refresh_mv_latest_risk();
```

### ObjectStore

* `filesystem` backend: rsync the mounted volume off-box on a cron.
* `s3`-compatible: use the vendor's snapshot/replication primitives
  (Aruba Cloud Object Storage, R2, B2 all expose lifecycle rules).

## Incident playbooks

### "All monitoring runs are empty"

1. Check `GET /ready` and `/health`. If 503, check the lifespan logs
   for migration failures.
2. Confirm the AOI grid exists: `SELECT COUNT(*) FROM grid_cells WHERE aoi_id = 'it-puglia';`
3. Confirm `cell_static_factors` has rows: same query against
   `cell_static_factors`. If 0, run `uv run limen bootstrap-static`.
4. Check Open-Meteo reachability — the `MeteoFetchExecutor` degrades
   silently to `None` on a 5xx but logs `integration.degraded`.

### "Alerts aren't firing"

1. Confirm at least one cell crosses `ALERT__MIN_LEVEL`. The Phase 5
   `GET /api/aoi/{id}/risk/latest` will surface the latest classes.
2. Check `alert_dispatches` for recent rows for that cell: if a row is
   within the dedup window, the executor suppressed the repeat by
   design. Adjust `ALERT__DEDUP_WINDOW_MINUTES` if needed.
3. Confirm channels are listed in `NOTIFICATIONS__ENABLED_CHANNELS`
   AND that each channel's creds are set. An unconfigured channel
   silently returns `False` — no error, no alert.
4. Inspect logs for `notifications.channel.error` (one channel raised)
   or `notifications.dispatch.empty` (no channels configured).

### "ISPRA IdroGEO sync is failing"

1. The weekly sync degrades gracefully on 5xx — it records an empty
   `dataset_versions` row with the empty hash and skips writes. The
   workflow stays usable; you just have stale IFFI/PAI until ISPRA is
   back.
2. Check `SELECT * FROM dataset_versions WHERE source = 'ispra' ORDER BY fetched_at DESC LIMIT 5;`.
3. Manually retry: `uv run python -m limen.integrations.idrogeo.sync_job` (or
   wait for the next Monday tick).

### "Map is blank"

1. Confirm pg_tileserv reaches the matview:
   `curl http://pg_tileserv:7800/index.json | jq '.[] | .name'`.
2. Confirm the matview has rows:
   `SELECT COUNT(*) FROM mv_latest_risk WHERE aoi_id = 'it-puglia';`.
3. If 0, run `SELECT refresh_mv_latest_risk();` or trigger a
   monitoring cycle (the `PersistResultExecutor` refreshes on exit).
4. Confirm `API__PG_TILESERV_URL` is set in the API container env.

### "FastAPI lifespan refuses to start"

Lifespan crashes on:

* DB unreachable → check `DB__CONNECTION_STRING` + the `postgres`
  container's healthcheck.
* Bad migration → checksum mismatch on an applied file. **Don't edit
  applied migrations** — add a new one.
* LLM resolver failure → set `LLM__PROVIDER` explicitly or remove the
  override so the precedence falls back to Ollama.

## Observability

Bring up the Grafana LGTM stack alongside the demo:

```bash
docker compose \
  -f infra/docker/docker-compose.demo.yml \
  -f infra/docker/docker-compose.observability.yml \
  up -d --build
```

Then point the API at it:

```env
API__OTEL_OTLP_ENDPOINT=http://observability:4318
API__OTEL_SERVICE_NAME=limen-api
```

Grafana UI → `http://localhost:3000` (anonymous Viewer). The provisioned
dashboards:

* **Limen — risk metrics (§3.9)** — the five OTel custom instruments.
* **Limen — system health** — DB pool, request rates, job runs, alert
  volume, recent logs.

## Versions + provenance

* The active scoring engine version is in `RegionalThresholds.model_version`
  (default `limen-deterministic-v1`). Every persisted
  `risk_assessments.pipeline_version` references it.
* External datasets are tagged by `dataset_versions(source, dataset, version)`.
* Open-Meteo / ISPRA / INGV / EFFIS open-data licenses + attribution
  are documented in the README "Attribution" section — propagate them
  to any public-facing rendering.
