---
paths:
  - "src/limen/api/jobs/**"
  - "src/limen/api/main.py"
  - "src/limen/cli/**"
  - "src/limen/agents/workflows/**"
  - "infra/docker/**"
---

# Cadenze e processo worker

Testo completo degli invarianti di cui `CLAUDE.md` tiene solo la riga breve:
la regola e il perché (misure, incidenti, issue). Vincolanti quanto la tabella.

| Topic | Rule |
|-------|------|
| Three cadences, not thirteen schedules (#78) | **Hourly** (`profile="hourly"`): V1 only — persistence and alerts, no LLM, no shadow. It is the path that must fit inside the tick, and the measurement says why: on 10,353 cells the two narrative nodes cost 140.3 s of a 156 s sweep against 0.88 s of actual scoring. The radar-nowcast and FIRMS triggers use the same profile. **Asynchronous** (`briefing_enrichment`, every `LLM__BRIEFING_INTERVAL_MINUTES`): the narrative for escalated AOIs, one at a time, written to `spiegazioni_regione` (migration 064), one row per (region, hazard) — never onto `risk_assessments`/`latest_risk`. It used to be attached to the sweep's rows, and both halves broke: the selective write (#135) leaves a quiet sweep with no rows ("no rows" on every region), and the sweep rewrites `latest_risk` every hour, wiping the text. The summary is built from `latest_risk` (`summary_for_region`); a text that is the deterministic fallback is stored with `ripiego = true` and the SPA does not attribute it to the AI. **Nightly** (`limen-nightly` at `SCHEDULER__NIGHTLY_HOUR_UTC`): shadow ML, drift, retrain, partitions, retention — in that order, each a `job_runs` row, a failing step never stopping the next. The **per-cell forecast** (`limen-forecast-history`) left the night: it runs at `SCHEDULER__FORECAST_CELLS_HOURS_UTC` (02/08/14/20 :20), because computed once at 02:00 it stayed on the map for 24 hours — on 7 October 2026 it showed Basilicata «molto alto» for Saturday's wildfire on the night's weather, while the morning runs brought rain and 84 % humidity and the same chain gave zero. The **forecast alerts** (`limen-forecast-monitoring`) run on the same hours at `FORECAST__MINUTE` (:50), after the per-cell run has refreshed `glofas_previsione`: a cron, not an interval from boot — every worker restart pushed the next run back, 19 hours without forecast alerts on 7-8 November 2026 (#489). `profile="nightly"` neither persists nor alerts: the night measures, it does not operate. The standalone schedules for drift, forecast history and cache cleanup are gone — reintroducing one makes it run twice. |
| APScheduler not pg_cron, **in the `worker` process** | Periodic jobs (hourly monitoring, weekly ISPRA sync, cache cleanup when configured) run via APScheduler so the same code works on Neon — but in the **`limen worker`** process, not the API (#77). `SCHEDULER__ENABLED=false` in the `api` container: one event loop cannot serve a public map and grind 312k cells at the same time, and `risk_scoring.py` still carries the comment from when it tried. The worker runs at **one replica**, fixed in the compose: `_sweep_lock` is an in-process lock, so two replicas would mean two concurrent sweeps. The fix is that line, not a distributed lock. |
