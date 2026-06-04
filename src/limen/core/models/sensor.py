"""Per-cell IoT sensor features (V1.5).

A :class:`SensorFeatures` row aggregates `sensor_observations` into one
hourly bucket. The engine reads this DTO via
:attr:`DynamicInputs.sensor_features`; when it is present, the
deterministic V1 path is augmented with:

* a **measured-over-modeled** override on rainfall + soil moisture +
  pore pressure (per §2.9);
* a **K** kinematic component bound to displacement velocity +
  Fukuzono inverse-velocity (also §2.9);
* a **hard-escalation** flag when acceleration exceeds the configured
  alarm — the alert dispatcher then bypasses the threshold gate.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SensorFeatures(BaseModel):
    """Hourly aggregate read from ``sensor_features_hourly`` per cell."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    bucket: datetime
    rainfall_mm: float | None = Field(default=None, ge=0.0)
    pore_pressure_kpa: float | None = Field(default=None, ge=0.0)
    soil_moisture: float | None = Field(default=None, ge=0.0, le=1.0)
    displacement_mm: float | None = None
    velocity_mmd: float | None = None
    acceleration_mmd2: float | None = None
    inverse_velocity: float | None = None
    sample_count: int = Field(default=0, ge=0)
    last_observation_at: datetime | None = None

    @property
    def has_kinematic_signal(self) -> bool:
        """True when at least one displacement-derived field is populated."""
        return any(
            v is not None
            for v in (
                self.velocity_mmd,
                self.acceleration_mmd2,
                self.inverse_velocity,
            )
        )

    @property
    def has_measured_meteo(self) -> bool:
        """True when a measured rainfall/soil/piezometer reading is available."""
        return any(
            v is not None
            for v in (
                self.rainfall_mm,
                self.pore_pressure_kpa,
                self.soil_moisture,
            )
        )


__all__ = ["SensorFeatures"]
