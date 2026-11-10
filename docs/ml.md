# V2 ML engine & MLOps

Phase 10 ships the V2 ML stack alongside V1, NOT instead of it. The
deterministic V1 engine remains the champion (drives alerts and
persisted scores) until a ML challenger clears the promotion gate on
honest, leakage-free metrics.

## Engine selection

`SCORING__ENGINE=deterministic|ml` flips between engines.
`SCORING__MODE=champion_only|shadow` selects whether the *other* engine
runs in parallel as a shadow challenger:

| ENGINE | MODE | What runs |
|---|---|---|
| `deterministic` | `champion_only` | V1 only — **default** |
| `deterministic` | `shadow` | V1 drives alerts; ML logs to `model_runs` |
| `ml` | `champion_only` | V2 drives alerts |
| `ml` | `shadow` | V2 drives alerts; V1 logs to `model_runs` |

Resolution lives in `limen.core.scoring.resolver.resolve_scoring_engine`.
If the MLflow registry doesn't have a Production model the resolver
**falls back to V1** and logs `scoring.ml_load_failed_fallback` — the
deterministic baseline is always live.

## Training pipeline (`limen train`)

```
training_samples (point-in-time correct, with split_block)
        │
        ▼
spatial-block CV folds (deterministic round-robin)
        │
        ▼
Optuna TPE over LightGBM hyperparams (objective = AUC-PR)
        │
        ▼
final LightGBM model on all data + booster log
        │
        ▼
isotonic calibration on OOF predictions  →  calibrator.pkl
        │
        ▼
SHAP TreeExplainer on the final booster   →  shap_explainer.pkl
        │
        ▼
MLflow run: params + metrics + model + artefacts
        │
        ▼
MLflow Model Registry: registered_model with `promoted` tag
```

* Spatial-block CV (never random) keeps autocorrelation between train
  and validation folds at zero — no leakage by construction.
* Class weights compensate the heavy 0/1 imbalance of landslide labels.
* Isotonic regression cuts Brier and gives operators well-calibrated
  probabilities.

## Promotion gate

Il gate ha due metà (#483), perché la validazione incrociata non può misurare
tutto: gira su un campione caso-controllo (un positivo ogni ~6 righe, quindi
hit rate e FAR lì sono ottimisti per costruzione) e non conosce l'ora
dell'evento (quindi niente anticipo). Fino alla #483 l'anticipo era passato
fisso a 0 contro 18 h: `promoted` era sempre `False`.

**`limen train`** — `gate_validazione` in `limen.ml.promozione`, tag
`gate_validazione` sul run (e `promoted=False`):

* `auc_pr_mean ≥ SCORING__PROMOTION_AUC_PR_MIN` (default 0.55)
* `brier_calibrated ≤ SCORING__PROMOTION_BRIER_MAX` (default 0.20)
* **`ML AUC-PR > V1 baseline AUC-PR`** on the SAME spatial-block CV partition.

`hit_rate_at_0_5` / `far_at_0_5` restano fra le metriche del run, ma sono del
campione caso-controllo e non entrano nel gate.

**`limen backtest` con `LIMEN_BACKTEST_SFIDANTE=<versione>`** — `gate_backtest`.
La versione registrata si carica in qualunque stage
(`MLScoringEngine.da_versione`); ogni AOI si rigioca prima con la V1, poi con lo
sfidante sugli stessi eventi, la stessa pioggia e gli stessi antecedenti, e lo
sfidante va in allerta **alla stessa quota di celle-ora della V1** (la sua
probabilità calibrata e l'indice V1 non hanno le stesse classi). Sommate le AOI:

* `hit_rate ≥ SCORING__PROMOTION_HIT_RATE_MIN` (default 0.70)
* `far ≤ SCORING__PROMOTION_FAR_MAX` (default 0.30)
* `anticipo medio ≥ SCORING__PROMOTION_LEAD_TIME_HOURS_MIN` (default 18.0)
* **eventi colti ≥ quelli della V1**, con una quota di celle-ora in allerta non
  superiore alla sua: la soglia dello sfidante sale al gradino successivo se il
  pari merito del calibratore isotonico sforerebbe la quota.

Sul run vanno `backtest_hit_rate`, `backtest_far`, `backtest_anticipo_ore`,
`backtest_quota_allertate`, `backtest_tasso_base` (celle con evento / celle: un
hit rate si legge solo accanto a questo) e le stesse tre della V1, più `backtest_finestra`, `backtest_aoi` e
`backtest_eventi` come tag (un verdetto su due eventi non è un esame); il tag
`promoted` è `gate_validazione AND gate_backtest`, anche sulla versione del
modello. Il report dello sfidante è `backtest_<aoi>_<inizio>_<fine>_sfidante.md`.

`limen shadow-report` aggiunge il confronto **per esito** sulla finestra in
ombra: la quota di coppie in cui il campione è almeno «Alto», la probabilità che
accende lo sfidante sulla stessa quota, eventi colti, celle accese e allarmi a
vuoto dei due. L'accordo di classe resta, marcato come indicativo.

Promotion to a stage is then an **operator decision** (`mlflow models
transition-stage`), not an automatic action — even a passing gate
only marks the run as eligible.

`TRAINING__AUTO_RETRAIN` (default **false**) permette al passo `retrain` della
pipeline notturna di lanciare `uv run limen train` in un sottoprocesso quando
il drift l'ha chiesto. Addestra e registra; **non promuove**. L'invariante non
si muove: acceso l'interruttore, la notte produce un run MLflow in più con il
suo tag, e la transizione di stage resta un comando che un umano digita.

Il registry vuole un backend a database: `SCORING__MLFLOW_TRACKING_URI` punta a
`postgresql://limen:limen@postgres:5432/mlflow` nel compose (database creato da
`infra/postgres/initdb/01-mlflow-db.sql`). Il file store è deprecato in MLflow
2.x e il registry dei modelli non ci funziona affatto — sqlite resta il default
solo per lo sviluppo locale.

## Champion-challenger shadow

**Lo shadow gira di notte, non ogni ora (#78).** `SCORING__MODE=shadow`
continua a significare "il challenger è configurato", ma il profilo `hourly`
del workflow non lo inserisce: LightGBM più SHAP per cella, ogni ora, su
~312.000 celle nazionali è il costo di un modello che il verdetto shadow dà
già per non promuovibile con queste feature. Il passo `shadow_ml` di
`api/jobs/nightly.py` lo esegue una volta per notte con `profile="nightly"`,
che scrive in `model_runs` e **non** persiste in `risk_assessments` né
dispaccia allerte: il notturno misura, non opera.

Conseguenza per chi legge i grafici: i dati del challenger sono **giornalieri**,
non orari. `SCORING__SHADOW_SHAP_TOP_K` ora morde solo lì, quindi alzarlo non
costa più niente allo sweep orario.

The workflow inserts `ShadowChallengerExecutor` only when
`SCORING__MODE=shadow` and the resolver produced a challenger. The
executor:

1. Re-uses the same `assemble_bundles()` output the champion saw.
2. Scores each bundle with the challenger.
3. Writes one row per cell to `model_runs` with `role='challenger'`.
4. **Returns the context unchanged.** The champion's `cell_results` /
   `assessment` / alerts are the only authoritative outputs.

Persistence failures inside the shadow are swallowed (logged) — the
shadow branch is never allowed to abort the workflow.

## EGMS InSAR (V2.1)

`limen sync-egms` populates `cell_insar_features` from the EGMS **Ortho L3**
product: the 100 m mean-velocity GeoTIFFs of the vertical (`U`) and
east-west (`E`) components, downloaded per 100 km tile and aggregated onto
the 1 km cells (p90 of the magnitude, median of each component, valid-pixel
count — migration 072). Credentials: `EGMS__SERVICE_KEY`, the CLMS service
key JSON (land.copernicus.eu → profile → «API Tokens»; it does not expire,
and each sync runs its own archive searches), or `EGMS__SERVICE_KEY_FILE`,
the path of that JSON. Signing, search bodies, response parsing and the
GeoTIFF extraction come from the
[`egms-client`](https://github.com/agent-engineering-studio/egms-client)
package; the traffic stays in `integrations/egms/clms.py` on
`fetch_with_retry`, like every outbound call (the package's own
`EgmsArchive` retries by itself, so Limen does not use it). Tiles already in
`EGMS__CARTELLA` (a persistent volume in Docker, `/var/lib/limen/egms`) are
never downloaded again, with the same file names as the package's cache. Cadence is yearly: the nightly `egms_release` step logs
`egms.release.nuova` when the archive lists a release newer than
`EGMS__RELEASE`; the operator bumps it and runs `limen sync-egms`.

## DL sub-model (V2.2)

`limen.ml.dl` ships a small 1D-CNN over a 1-week hourly rainfall
window. Trained offline (PyTorch, `dl` optional group), exported to
ONNX, and served via `onnxruntime` (in the `ml` group) by
`DLMeteoProbability`. Missing model OR missing onnxruntime → neutral
0.5 probability.

## Drift monitoring + retraining trigger

`enable_drift_monitoring=true` schedules `JOB_DRIFT_MONITOR` every
`MONITORING__DRIFT_CHECK_HOURS` (default 24h). One tick computes:

* **PSI** between the training distribution and recent live values;
* **KS** distance between the same;
* **Prediction drift** (absolute change in mean predicted probability).

PSI and KS are computed for **every feature** of the vector the challenger
persisted (`MONITORING__DRIFT_FEATURES`, a JSON list, narrows it; #482), and
the trigger reads the worst one (`drift.peggiore`: a feature over a threshold
first, then the highest PSI). The log line lists the features over threshold
and the PSI of each.

## Feature schemas (#482)

`ml/dataset.py` holds one ordered schema per hazard (`FEATURES_BY_HAZARD`):
landslide `CANONICAL_FEATURES`, wildfire `WILDFIRE_FEATURES`, flood
`FLOOD_FEATURES` (ISPRA hydraulic class, sealed soil, height above the valley
floor, elevation, slope, TWI — before #482 flood fell back on the landslide
schema). New landslide columns go **at the tail** (a registered model reads
its own `feature_names.json`): `seismic.pga_max_g` — the max PGA of the
earthquakes that shook the cell in `SeismicCheck`'s window, up to the sample
time only — and `static.imperviousness_norm`. Every schema name must be
mapped by `ml_engine._bundle_to_feature_row`, or it is served as a silent
zero; `tests/unit/test_feature_store_482.py` checks it. Known gap: the
`insar.*` features are trained on `cell_insar_features` but served as 0,
because the bundle carries no InSAR — the EGMS vertical/east components are
not added until it does.

A threshold breach OR enough new IFFI events triggers
`RetrainingTrigger(should_retrain=True, reason=...)`. The trigger
**only signals**; operators still run `limen train` and re-apply the
promotion gate manually.

## Offline measurements (`limen misura`, #480)

Before a new per-cell signal enters an engine or the feature set, measure
whether it separates events at all — read-only, with one command:

```bash
uv run limen misura --pericolo wildfire --feature slope_deg \
    --stima 2021-2023 --verifica 2024-2026
uv run limen misura --pericolo flood --feature quota_sul_fondo_m \
    --stima 2023-2024 --verifica 2025-2026
```

- **Truth**: wildfire = cells covered ≥ 25 % by EFFIS perimeters in the period;
  flood = cells covered ≥ 1 % by Copernicus EMS flooded areas, over the cells
  inside an EMS observation mask only (outside nobody looked). `--copertura`
  overrides.
- **Strata**: 0.25° weather node × elevation band (200 / 500 / 1000 m). The
  AUC is computed inside each stratum with both classes and averaged with the
  number of positive-negative pairs as weight: a feature that only tells the
  North from the South scores 0.5.
- **Observed/expected** per feature class, with expected = the base rate of
  each cell's stratum. Classes are quantiles of the **estimation** period and
  are applied unchanged to the **verification** period.
- The feature must be a numeric column of `cell_static_factors`. Report in
  `LIMEN_REPORTS_DIR` (default `reports/`); nothing is written to the DB.
- Code: `limen.ml.misure` (pure numpy), `data/repos/misure_repo.py`,
  `cli/misura.py`.

Not covered yet: scoring a cell through the real engine offline (needs the
weather of each day), and the old #295/#419/#420 tables, whose session scripts
are gone — re-measure with this command rather than trust their numbers.

## Report provenance and reference reports (#481)

Every measurement command (`backtest`, `backtest-flood`, `backtest-wildfire`,
`backtest-cosismico`, `calibrate`, `verifiche-report`, `shadow-report`,
`misura`) writes its report through `limen.cli.provenienza.scrivi_report`: a
closing **Provenienza** section and a sibling `<report>.provenienza.json` with
the commit (`LIMEN_COMMIT`, set by the CI image build; the checkout's
`git rev-parse` locally, `+modifiche` if `src/` is dirty), the `model_version`
of the three hazards, the command line and the `LIMEN_*` / `SCORING__*` /
`FORECAST__*` / `BACKTEST__*` variables set — never secrets, and local paths
shown as `<percorso locale>`.

```bash
uv run limen archivia-report reports/backtest_wildfire_it-sicilia_2024-06-01_2024-09-30.md
```

copies report and provenance into `docs/misure/` and rewrites its index
(`README.md`, newest first). A report without provenance predates #481 and is
refused: re-run it. A PR that changes a `model_version` re-runs the reference
backtests and archives them (PR template checklist). Not covered yet: static
data fingerprints and truth-catalogue versions in the header, and the Zenodo
deposit.

## Where things live

| Path | Purpose |
|---|---|
| `src/limen/core/scoring/base.py` | `ScoringEngine` Protocol |
| `src/limen/core/scoring/resolver.py` | engine selection + shadow challenger |
| `src/limen/core/scoring/ml_engine.py` | V2 LightGBM-backed engine + MLflow loader |
| `src/limen/ml/feature_store.py` | offline sampler + spatial-block grid |
| `src/limen/ml/train.py` | Optuna + LightGBM + isotonic + SHAP + MLflow |
| `src/limen/ml/baseline.py` | V1 baseline scoring on training samples |
| `src/limen/ml/metrics.py` | AUC-PR / Brier / hit-rate-FAR / lead time |
| `src/limen/ml/dl/` | DL sub-model (model + train + serve) |
| `src/limen/ml/monitoring/` | drift primitives + RetrainingTrigger |
| `src/limen/integrations/egms/` | Copernicus EGMS InSAR sync |
| `src/limen/agents/executors/shadow_challenger.py` | shadow executor |
