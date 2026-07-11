from limen.core.models.risk import RiskLevel
from limen.report.reasons import plain_summary, verdict


def test_dominant_driver_is_rain_when_meteo_highest() -> None:
    text = plain_summary(s=0.1, m=0.8, e=0.0, f=0.0, h=0.0)
    assert "pioggia" in text.lower()
    assert "verso l'alto" in text


def test_no_rain_notes_historical_fragility() -> None:
    text = plain_summary(s=0.6, m=0.0, e=0.0, f=0.0, h=0.0)
    assert "versante" in text.lower()
    assert "Non c'è pioggia" in text


def test_verdict_high_is_warn() -> None:
    v = verdict(RiskLevel.High)
    assert v.tone == "warn"
    assert "attenzionare" in v.text.lower()


def test_verdict_moderate_is_watch() -> None:
    assert verdict(RiskLevel.Moderate).tone == "watch"


def test_verdict_low_and_none_are_ok() -> None:
    assert verdict(RiskLevel.Low).tone == "ok"
    assert verdict(RiskLevel.None_).tone == "ok"


def test_rain_low_incide_poco() -> None:
    text = plain_summary(s=0.6, m=0.1, e=0.0, f=0.0, h=0.0)
    assert "incide poco" in text


def test_rain_moderate_in_modo_moderato() -> None:
    text = plain_summary(s=0.6, m=0.3, e=0.0, f=0.0, h=0.0)
    assert "in modo moderato" in text


def test_no_dominant_driver_when_all_below_gate() -> None:
    text = plain_summary(s=0.0, m=0.0, e=0.0, f=0.0, h=0.0)
    assert "nasce soprattutto" not in text
    assert "Non c'è pioggia" in text
