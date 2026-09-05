"""Lettura di mezzogiorno per la catena FWI (issue #61).

La catena è definita su **una** osservazione al giorno, a mezzogiorno locale
(Van Wagner 1987 §2): i codici modellano l'umidità del combustibile nell'ora
più calda e secca. Una media giornaliera sottostimerebbe sistematicamente il
pericolo, quindi la selezione dell'ora è parte della correttezza, non un
dettaglio di parsing.
"""

from __future__ import annotations

import datetime as dt

from limen.integrations.openmeteo.dtos import MeteoSnapshot, WeatherSample


def _hour(h: int, *, day: int = 15, temp: float | None = 20.0, rain: float = 0.0) -> WeatherSample:
    return WeatherSample(
        timestamp=dt.datetime(2026, 7, day, h, tzinfo=dt.UTC),
        precipitation_mm=rain,
        temperature_c=temp,
        relative_humidity_pct=40.0,
        wind_speed_kmh=10.0,
    )


def _snapshot(samples: list[WeatherSample]) -> MeteoSnapshot:
    return MeteoSnapshot(
        centroid_lon=16.0,
        centroid_lat=41.0,
        window_start=dt.datetime(2026, 7, 14, tzinfo=dt.UTC),
        window_end=dt.datetime(2026, 7, 15, 23, tzinfo=dt.UTC),
        samples=samples,
    )


def test_the_hottest_hour_is_picked_not_the_daily_mean() -> None:
    """Il campione scelto è quello più vicino a mezzogiorno, non una media."""
    snap = _snapshot([_hour(6, temp=12.0), _hour(12, temp=34.0), _hour(20, temp=18.0)])
    obs = snap.noon_observation(dt.date(2026, 7, 15))
    assert obs is not None
    assert obs.temperature_c == 34.0


def test_the_nearest_hour_wins_when_noon_itself_is_missing() -> None:
    """Le finestre di archivio hanno buchi: 11:00 vale più di 06:00."""
    snap = _snapshot([_hour(6, temp=12.0), _hour(11, temp=30.0), _hour(23, temp=15.0)])
    obs = snap.noon_observation(dt.date(2026, 7, 15))
    assert obs is not None
    assert obs.temperature_c == 30.0


def test_rain_is_summed_over_the_24_h_before_noon_across_the_day_boundary() -> None:
    """La pioggia del giorno FWI finisce a mezzogiorno, non a mezzanotte.

    Metà di quella finestra sta nel giorno civile precedente: sommare per
    data solare perderebbe un temporale notturno, cioè esattamente quello che
    spegne il pericolo del mattino dopo.
    """
    snap = _snapshot(
        [
            _hour(23, day=14, rain=10.0),  # dentro la finestra
            _hour(6, rain=5.0),  # dentro
            _hour(12, rain=1.0),  # dentro (l'ora stessa)
            _hour(18, rain=99.0),  # dopo mezzogiorno: fuori
            _hour(10, day=14, rain=77.0),  # oltre 24 h prima: fuori
        ]
    )
    obs = snap.noon_observation(dt.date(2026, 7, 15))
    assert obs is not None
    assert obs.rain_24h_mm == 16.0


def test_a_day_without_the_three_variables_yields_no_observation() -> None:
    """Assente ≠ zero. Uno zero inventato sarebbe una giornata di asciugatura
    finta, e la ricorsione se la porterebbe dietro per settimane."""
    snap = _snapshot([_hour(12, temp=None)])
    assert snap.noon_observation(dt.date(2026, 7, 15)) is None


def test_a_snapshot_cached_before_fire_weather_existed_still_parses() -> None:
    """Le tre colonne sono opzionali: una voce di cache vecchia non deve far
    esplodere il parsing, deve solo non produrre osservazioni."""
    old = WeatherSample(timestamp=dt.datetime(2026, 7, 15, 12, tzinfo=dt.UTC), precipitation_mm=2.0)
    assert old.has_fire_weather is False
    assert _snapshot([old]).noon_observation(dt.date(2026, 7, 15)) is None
