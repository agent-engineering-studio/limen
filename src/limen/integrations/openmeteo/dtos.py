"""Pydantic DTOs for Open-Meteo responses.

The DTOs are intentionally close to the API's hourly schema: parsing
stays simple, and downstream code (the scoring engine in Phase 3) can do
its own aggregation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

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
    # Fire weather (#61). Optional like every other column: a snapshot cached
    # before these existed, or an archive window that lacks them, must still
    # parse -- the FWI step then reports no observation for that day.
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_kmh: float | None = None

    @field_validator("precipitation_mm")
    @classmethod
    def _non_negative_precip(cls, v: float) -> float:
        return max(v, 0.0)

    @property
    def has_fire_weather(self) -> bool:
        return (
            self.temperature_c is not None
            and self.relative_humidity_pct is not None
            and self.wind_speed_kmh is not None
        )


class FireWeatherObservation(BaseModel):
    """The four daily inputs of the FWI chain, at local noon.

    Lives here rather than in the scoring package because it is a *reading*
    of the weather, not an interpretation of it: the pure FWI module takes
    these numbers and knows nothing about where they came from.
    """

    model_config = {"frozen": True}

    day: date
    temperature_c: float
    relative_humidity_pct: float = Field(..., ge=0.0, le=100.0)
    wind_speed_kmh: float = Field(..., ge=0.0)
    rain_24h_mm: float = Field(..., ge=0.0)


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

    def noon_observation(self, day: date, *, noon_hour: int = 12) -> FireWeatherObservation | None:
        """Fire weather at local noon on ``day``, with the rain of the 24 h before it.

        The FWI chain is defined on a single daily observation taken at local
        noon (Van Wagner 1987 §2), not on a daily mean: the codes model the
        moisture of fuels at the hottest, driest hour, and averaging would
        systematically understate the danger.

        Snapshots are requested in UTC. Italy is UTC+1/+2, so the sample
        nearest ``noon_hour`` UTC is within an hour of solar noon -- close
        enough for the fuel-moisture equations, and it avoids carrying a
        timezone database into a pure DTO.

        Returns ``None`` when the day has no sample carrying all three
        variables: a missing observation must not silently become a zero,
        which the recursive codes would then carry forward for days.
        """
        candidates = [s for s in self.samples if s.timestamp.date() == day and s.has_fire_weather]
        if not candidates:
            return None
        noon = min(candidates, key=lambda s: abs(s.timestamp.hour - noon_hour))
        window_start = noon.timestamp - timedelta(hours=24)
        rain = sum(
            s.precipitation_mm for s in self.samples if window_start < s.timestamp <= noon.timestamp
        )
        # mypy: `has_fire_weather` already proved these are not None.
        assert noon.temperature_c is not None
        assert noon.relative_humidity_pct is not None
        assert noon.wind_speed_kmh is not None
        return FireWeatherObservation(
            day=day,
            temperature_c=noon.temperature_c,
            relative_humidity_pct=min(max(noon.relative_humidity_pct, 0.0), 100.0),
            wind_speed_kmh=max(noon.wind_speed_kmh, 0.0),
            rain_24h_mm=float(rain),
        )
