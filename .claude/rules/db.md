---
paths:
  - "src/limen/data/**"
  - "src/limen/api/jobs/**"
---

# Tabelle partizionate

Testo completo degli invarianti di cui `CLAUDE.md` tiene solo la riga breve:
la regola e il perché (misure, incidenti, issue). Vincolanti quanto la tabella.

| Topic | Rule |
|-------|------|
| Hot tables are partitioned | `risk_assessments` and `model_runs` are RANGE-partitioned by **UTC** day on `computed_at`; the PK includes the partition key. Retention is `drop_expired_partitions()`, never `DELETE`. `ensure_partitions()` must run before a sweep writes: the `limen-partitions` job owns it (registered **unconditionally** — never fold it back into the cache-cleanup job, which is skipped under the pg_cron backend), the API retries it best-effort on boot, `limen partitions` runs it on demand. Rows in a `*_default` partition are a bug: retention cannot reach them. |
