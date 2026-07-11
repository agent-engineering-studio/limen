from limen.report.builder import assessment_signature, build_id_for


def test_signature_is_stable_and_order_independent() -> None:
    a = {"cells": [{"cell_id": "a", "score": 0.5}, {"cell_id": "b", "score": 0.9}]}
    b = {"cells": [{"cell_id": "b", "score": 0.9}, {"cell_id": "a", "score": 0.5}]}
    assert assessment_signature(a) == assessment_signature(b)


def test_build_id_from_valuation_time() -> None:
    assert build_id_for("2026-07-11T08:00:00+00:00") == "2026-07-11T0800Z"
