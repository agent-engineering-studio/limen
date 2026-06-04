"""SensorThings-aligned Pydantic v2 schema for one in-situ observation.

Carried over MQTT as JSON. Versioned via :attr:`Observation.contract_version`
so future schema changes can ship a new value without forcing every
device to upgrade in lock-step.

The shape mirrors OGC SensorThings (ISO 19156 O&M):

* ``thing_id``           → SensorThings Thing identifier
* ``observed_property``  → ObservedProperty enum
* ``phenomenon_time``    → the instant the observation refers to
* ``result_value`` +
  ``result_unit``        → the value + its UCUM unit code
* ``raw_value``          → pre-calibration reading (audit only)

The UCUM units listed below are the canonical ones for each
ObservedProperty. Devices MAY send compatible units (e.g. "m" for
displacement) — the ingestor's calibration step is the right place to
convert to the canonical unit before persistence.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ObservedProperty(StrEnum):
    """Six supported observed properties for V1.5.

    Maps 1:1 to the rollup columns in ``sensor_features_hourly``.
    """

    RAINFALL = "rainfall"
    PORE_PRESSURE = "pore_pressure"
    SOIL_MOISTURE = "soil_moisture"
    DISPLACEMENT = "displacement"
    VELOCITY = "velocity"
    ACCELERATION = "acceleration"


# UCUM unit codes considered canonical for each property. Devices may
# send compatible units; calibration converts to these before storage.
CANONICAL_UNITS: dict[ObservedProperty, str] = {
    ObservedProperty.RAINFALL: "mm",
    ObservedProperty.PORE_PRESSURE: "kPa",
    ObservedProperty.SOIL_MOISTURE: "m3/m3",
    ObservedProperty.DISPLACEMENT: "mm",
    ObservedProperty.VELOCITY: "mm/d",
    ObservedProperty.ACCELERATION: "mm/d2",
}


class Observation(BaseModel):
    """One observation as it lands over MQTT."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    # Schema version — bump for breaking changes. The ingestor refuses
    # contract versions it does not understand.
    contract_version: str = Field(default="v1", pattern=r"^v\d+$")
    thing_id: str = Field(..., min_length=1)
    observed_property: ObservedProperty
    phenomenon_time: datetime
    result_value: float
    result_unit: str = Field(..., min_length=1, max_length=32)
    raw_value: float | None = None
    # Free-form per-device metadata (battery, RSSI, firmware...). Kept
    # small — anything heavy belongs in a separate telemetry stream.
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("phenomenon_time")
    @classmethod
    def _require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("phenomenon_time must be timezone-aware (use UTC)")
        return v

    @property
    def canonical_unit(self) -> str:
        return CANONICAL_UNITS[self.observed_property]


__all__ = ["CANONICAL_UNITS", "Observation", "ObservedProperty"]
