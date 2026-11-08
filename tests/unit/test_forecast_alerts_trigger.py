"""Gli avvisi di previsione girano a orari fissi: un riavvio non li sposta (#489)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from apscheduler.triggers.cron import CronTrigger

from limen.api.jobs.registration import _forecast_alerts_trigger
from limen.config.settings import ForecastSettings


def _prossime(trigger: CronTrigger, n: int) -> list[datetime]:
    fuochi = [trigger.next() for _ in range(n)]
    assert all(f is not None for f in fuochi)
    return [f for f in fuochi if f is not None]


def test_default_hours_follow_the_per_cell_forecast() -> None:
    cfg = ForecastSettings()
    assert cfg.hours_utc == [2, 8, 14, 20]
    assert cfg.minute == 50
    assert cfg.interval_hours == 6


def test_restart_at_0910_fires_at_1450_not_one_interval_later() -> None:
    avvio = datetime(2026, 11, 7, 9, 10, tzinfo=UTC)
    fuochi = _prossime(_forecast_alerts_trigger(ForecastSettings(), start_time=avvio), 4)
    assert fuochi == [
        datetime(2026, 11, 7, 14, 50, tzinfo=UTC),
        datetime(2026, 11, 7, 20, 50, tzinfo=UTC),
        datetime(2026, 11, 8, 2, 50, tzinfo=UTC),
        datetime(2026, 11, 8, 8, 50, tzinfo=UTC),
    ]


@pytest.mark.parametrize(
    "riavvio",
    [
        datetime(2026, 11, 7, 9, 10, tzinfo=UTC),
        datetime(2026, 11, 7, 13, 0, tzinfo=UTC),
        datetime(2026, 11, 7, 14, 49, 59, tzinfo=UTC),
    ],
)
def test_next_fire_depends_only_on_the_clock(riavvio: datetime) -> None:
    trigger = _forecast_alerts_trigger(ForecastSettings(), start_time=riavvio)
    assert trigger.next() == datetime(2026, 11, 7, 14, 50, tzinfo=UTC)


def test_seven_days_give_four_runs_a_day() -> None:
    inizio = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    fine = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)
    fuochi = [
        f
        for f in _prossime(_forecast_alerts_trigger(ForecastSettings(), start_time=inizio), 40)
        if f < fine
    ]
    assert len(fuochi) == 28


def test_hours_and_minute_come_from_the_settings() -> None:
    cfg = ForecastSettings(hours_utc=[20, 5, 5], minute=7)
    assert cfg.interval_hours == 15
    avvio = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
    assert _prossime(_forecast_alerts_trigger(cfg, start_time=avvio), 2) == [
        datetime(2026, 11, 7, 20, 7, tzinfo=UTC),
        datetime(2026, 11, 8, 5, 7, tzinfo=UTC),
    ]


def test_env_var_sets_the_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORECAST__HOURS_UTC", "[3, 15]")
    monkeypatch.setenv("FORECAST__MINUTE", "45")
    from limen.config.settings import Settings

    cfg = Settings().forecast
    assert cfg.hours_utc == [3, 15]
    assert cfg.minute == 45
    assert cfg.interval_hours == 12
