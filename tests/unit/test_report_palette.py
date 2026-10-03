from itertools import pairwise

from limen.core.models.risk import RiskLevel
from limen.report.palette import RISK_CLASSES, color_for, label_for, text_color_for


def test_five_classes_cover_unit_interval() -> None:
    assert len(RISK_CLASSES) == 5
    assert RISK_CLASSES[0].range[0] == 0.0
    assert RISK_CLASSES[-1].range[1] == 1.0
    for a, b in pairwise(RISK_CLASSES):
        assert a.range[1] == b.range[0]


def test_color_and_label_by_level() -> None:
    assert color_for(RiskLevel.VeryHigh) == "#e33f5a"
    assert color_for(RiskLevel.None_) == "#151c25"
    assert label_for(RiskLevel.High) == "Alto"


def test_mirrors_the_spa_palette() -> None:
    # Lo stesso colore deve dire la stessa classe nella SPA e nel report.
    import re
    from pathlib import Path

    ts = (Path(__file__).parents[2] / "frontend/src/lib/risk-colors.ts").read_text()
    blocco = ts[ts.index("export const RISK_CLASSES") : ts.index("] as const;")]
    assert re.findall(r'color: "(#[0-9a-f]{6})"', blocco) == [c.color for c in RISK_CLASSES]


def test_badge_text_reads_on_the_class_colour() -> None:
    assert text_color_for(RiskLevel.Low) == "#ffffff"
    assert text_color_for(RiskLevel.Moderate) == "#1a0f05"
