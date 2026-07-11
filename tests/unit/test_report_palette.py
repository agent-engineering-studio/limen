from itertools import pairwise

from limen.core.models.risk import RiskLevel
from limen.report.palette import RISK_CLASSES, color_for, label_for


def test_five_classes_cover_unit_interval() -> None:
    assert len(RISK_CLASSES) == 5
    assert RISK_CLASSES[0].range[0] == 0.0
    assert RISK_CLASSES[-1].range[1] == 1.0
    for a, b in pairwise(RISK_CLASSES):
        assert a.range[1] == b.range[0]


def test_color_and_label_by_level() -> None:
    assert color_for(RiskLevel.VeryHigh) == "#bd0026"
    assert color_for(RiskLevel.None_) == "#ffffb2"
    assert label_for(RiskLevel.High) == "Alto"
