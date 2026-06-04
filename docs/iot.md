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

All knobs live under the `LIMEN_IOT__*` env namespace (see
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
