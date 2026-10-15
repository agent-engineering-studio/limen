# In-situ IoT — V1.5

V1.5 adds a hybrid MQTT / SensorThings ingestion path that feeds the
deterministic engine with directly-measured rainfall, pore pressure,
soil moisture, and displacement. The whole subsystem is gated by the
`enable_insitu` setting; with it off the system is byte-for-byte the
V1 behaviour (the `RiskScore` is identical down to the last bit).

## Topic taxonomy

```
limen/v1/{region}/{site}/{thing}/{datastream}/obs
limen/v1/{region}/{site}/{thing}/status            ← LWT
```

Six observed properties, one datastream each: `rainfall`,
`pore_pressure`, `soil_moisture`, `displacement`, `velocity`,
`acceleration`. Canonical UCUM units per property are listed in
`src/limen/integrations/iot/schemas.py::CANONICAL_UNITS`.

## Pipeline

1. **Ingestor** (`limen.integrations.iot.mqtt_ingestor`) subscribes to
   `limen/v1/+/+/+/+/obs` at QoS 1 with the LWT pattern.
2. Each message is parsed (`Observation.model_validate_json`),
   topic-thing reconciled, the SensorThings `Thing` looked up,
   calibrated (per-property `scale`/`offset` from the device's JSON),
   passed through QC (range / spike / flatline / gap / unit), and
   persisted into `sensor_observations`.
3. **Rollup** (`limen.api.jobs.iot_rollup`) runs every
   `iot.rollup_minutes` (default 10 min) and aggregates the previous
   hour into `sensor_features_hourly` — including the displacement
   velocity (least-squares slope), acceleration (finite difference
   between consecutive hourly velocities), and inverse-velocity
   (Fukuzono input).
4. **Workflow** — when `enable_insitu` is true the conditional
   `SensorFetchExecutor` reads the latest `sensor_features_hourly` row
   per cell and stores it on `MonitoringContext.sensor_features_by_cell`.
   The engine then runs the kinematic K component (`compute_kinematic`)
   and the measured-over-modeled override on M (Caine, API, soil).
5. **Hard escalation** — when acceleration ≥ `acceleration_alarm_mmd2`
   or inverse-velocity ≤ `inverse_velocity_alarm`, the engine sets
   `RiskScore.hard_escalation = True`; `EscalationGateExecutor` records
   the cells and `AlertDispatchExecutor` bypasses the `min_level`
   threshold for them (precursor signals are dispatched even below the
   aggregate alert level).

## Trust levels (#251)

Every device in `sensor_devices` carries a `livello` (migration 075):

| Level | Who | Where its measurements go |
|---|---|---|
| 0 · observer | anyone, after registration | `sensor_observations` only: archive, verifications, comparison with the DPC radar |
| 1 · verified | promoted after weeks of agreement with the radar | as level 0 for now; #258 will let it only *raise* the rainfall in M, with a quorum of distinct registrants and a cap |
| 2 · institutional | public bodies, Civil Protection, universities | the hourly rollup, hence the M override, K and `hard_escalation` |

Devices registered before the migration were backfilled with 2 and keep
scoring exactly as before; from then on the column defaults to 0, so a
registration that forgets the level leaves the device out of scoring.
`upsert_many` writes the level on insert only: a registry re-sync can
neither promote nor demote a device. The filter lives in one place, the rollup's
device query: `sensor_features_hourly` is the only table the engine
reads sensors from, and only level-2 devices reach it. A third-party
rain gauge clogged at zero cannot lower M, and a bumped third-party
extensometer cannot bypass `min_level`. A cell whose only devices are
level 0 or 1 gets no row, so the engine runs the plain V1 path there.

## Freshness (#262)

`SensorFetchExecutor` reads a cell's latest rollup row only if its last
observation falls in `(valuation_time - IOT__MAX_AGE_MINUTES,
valuation_time]` (default 120 min). Older, the row is not a measurement
any more and the cell goes back to the model: a gauge that read zero and
then went silent cannot hold M down, and an extensometer that stopped
after an accelerating hour cannot keep `hard_escalation` on. A replay
never reads observations from after the time it values.

## Storage

- `sensor_devices` — SensorThings `Thing` registry (cell binding +
  calibration JSON + lifecycle status).
- `sensor_observations` — raw stream, **partitioned by month** on
  `phenomenon_time`. Migration 009 seeds ±6 monthly partitions; the
  APScheduler job `limen-iot-partition-rollover` extends the rolling
  window once a month.
- `sensor_features_hourly` — per-cell aggregate the workflow reads.

## Regime renormalization

On monitored cells the V1 weighted sum is rescaled to

```
risk = w_K * K + (1 - w_K) * (w_S * S + w_M * M' + w_E * E + w_F * F + w_H * H)
```

with `w_K = kinematic.weights.k` from the YAML (default 0.20). On
unmonitored cells the formula reduces to V1's plain weighted sum.

## Quality control

`run_qc()` aggregates the five checks and returns the **worst** label:
`ok` (0) < `gap` < `flatline` < `spike` < `range` < `unit`. Only `ok`
observations contribute to the hourly rollup.

## Configuration

All knobs live under the `IOT__*` env namespace (see
`Settings.IotSettings`). The YAML adds a `kinematic:` block — leave it
out to deactivate K entirely without touching code.

## Tests

- `tests/unit/test_iot_qc.py` — schema strictness + QC severity rules.
- `tests/unit/test_iot_mqtt_ingestor.py` — topic parser + calibrator +
  the message handler with mocked repos.
- `tests/unit/test_v15_kinematic.py` — K monotonicity, hard
  escalation, measured-over-modeled, and the **invariance** suite that
  proves V1.5(disabled) == V1.
- `tests/integration/test_iot_sensor_pipeline.py` — repos + the rollup
  job against the real PostGIS container.
