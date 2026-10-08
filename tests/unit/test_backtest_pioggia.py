"""Il backtest frane non misura il motore su una pioggia che non è arrivata (#122)."""

from __future__ import annotations


def test_la_pioggia_tutta_a_zero_non_e_una_misura() -> None:
    """Un modello che l'archivio non serve risponde con valori nulli, letti
    come 0 mm: il 7 ottobre 2026 il backtest frane ha misurato così un
    novembre ligure asciutto, quello delle alluvioni del 2019."""
    from datetime import UTC, datetime

    from limen.cli.backtest import rain_was_measured
    from limen.core.models.risk import RainfallSample

    t = datetime(2019, 11, 23, tzinfo=UTC)
    asciutto = [[RainfallSample(timestamp=t, precipitation_mm=0.0)] for _ in range(3)]
    assert rain_was_measured(asciutto) is False
    piove = [*asciutto, [RainfallSample(timestamp=t, precipitation_mm=4.2)]]
    assert rain_was_measured(piove) is True


def test_gli_antecedenti_come_li_legge_lo_sweep() -> None:
    """Pioggia dei 30 giorni fino al giorno compreso, umidità media sulle 48 ore."""
    from datetime import UTC, datetime, timedelta

    from limen.cli.backtest import Antecedenti
    from limen.integrations.openmeteo.dtos import WeatherSample

    t0 = datetime(2019, 11, 1, tzinfo=UTC)
    campioni = [
        WeatherSample(
            timestamp=t0 + timedelta(hours=h),
            precipitation_mm=1.0 if h % 24 == 12 else 0.0,
            soil_moisture_0_7_cm=0.20 if h < 24 * 33 else 0.40,
        )
        for h in range(24 * 35)
    ]
    a = Antecedenti.da_serie(campioni)
    t = t0 + timedelta(days=34, hours=12)
    # Un millimetro al giorno, trenta giorni fino al giorno di t compreso.
    assert a.api(t) == 30.0
    # Le ultime 48 ore: metà a 0,20 e metà a 0,40, quasi.
    suolo = a.suolo(t)
    assert suolo is not None and 0.30 < suolo < 0.40
    # Prima che la serie cominci non si inventa niente.
    assert a.api(t0 - timedelta(days=60)) is None
    assert a.suolo(t0 - timedelta(days=60)) is None
