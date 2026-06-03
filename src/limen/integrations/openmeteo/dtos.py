"""Pydantic DTOs for Open-Meteo responses.

The DTOs are intentionally close to the API's hourly schema: parsing
stays simple, and downstream code (the scoring engine in Phase 3) can do
its own aggregation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class WeatherSample(BaseModel):
    """One hourly observation at a meteo-cell centroid."""

    model_config = {"frozen": True}

    timestamp: datetime
    precipitation_mm: float = 0.0
    soil_moisture_0_7_cm: float | None = None
    soil_moisture_7_28_cm: float | None = None
    snowfall_cm: float | None = None
    snow_depth_m: float | None = None

    @field_validator("precipitation_mm")
    @classmethod
    def _non_negative_precip(cls, v: float) -> float:
        return max(v, 0.0)


class MeteoSnapshot(BaseModel):
    """A timeseries window for a single meteo-cell centroid.

    Source data are at ~9 km spatial resolution; multiple risk cells (1 km²)
    share the same snapshot. The caller clusters by centroid to amortise.
    """

    centroid_lon: float
    centroid_lat: float
    window_start: datetime
    window_end: datetime
    samples: list[WeatherSample] = Field(default_factory=list)
    source: str = "open-meteo"
    api_version: str | None = None

    @property
    def total_precipitation_mm(self) -> float:
        return float(sum(s.precipitation_mm for s in self.samples))

    @property
    def max_soil_moisture_0_7_cm(self) -> float | None:
        values = [
            s.soil_moisture_0_7_cm for s in self.samples if s.soil_moisture_0_7_cm is not None
        ]
        return max(values) if values else None
