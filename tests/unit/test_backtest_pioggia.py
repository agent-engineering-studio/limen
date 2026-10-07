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
