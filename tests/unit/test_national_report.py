"""Unit checks for the national report rendering + payload wrapping."""

from __future__ import annotations

from limen.api.jobs.daily_report import build_report_payload
from limen.core.models.risk import RiskLevel
from limen.mcp.tools import render_national_report_it

_REPORT = {
    "generated_at": "2026-07-06T06:00:00+00:00",
    "regions": [
        {"aoi_id": "it-campania", "cells_scored": 100, "high_or_above": 3, "moderate": 10},
        {"aoi_id": "it-puglia", "cells_scored": 200, "high_or_above": 0, "moderate": 5},
    ],
    "totals": {"regions": 2, "cells": 300, "high_or_above": 3, "moderate": 15},
    "top_cells": [
        {"cell_id": "it-campania|1|1", "aoi_id": "it-campania", "score": 0.81, "level": "High"}
    ],
    "ml_top_cells": [
        {"cell_id": "it-puglia|2|2", "aoi_id": "it-puglia", "probability": 0.64, "level": "High"}
    ],
    "alerts_24h": 4,
    "forecast_alerts_24h": 1,
}


def test_render_is_deterministic_and_faithful() -> None:
    text = render_national_report_it(_REPORT)
    assert text == render_national_report_it(_REPORT)
    assert "300 monitorate in 2 regioni" in text
    assert "Campania (3)" in text
    assert "0.81" in text and "64%" in text
    assert "4 allerte operative, 1 allerte previsionali" in text
    # Multi-riga: un fatto per riga, leggibile da non esperti.
    assert text.count("\n") >= 5


def test_render_quiet_country() -> None:
    quiet = {
        **_REPORT,
        "regions": [r | {"high_or_above": 0} for r in _REPORT["regions"]],
        "totals": {**_REPORT["totals"], "high_or_above": 0},
        "top_cells": [],
        "ml_top_cells": [],
    }
    text = render_national_report_it(quiet)
    assert "Nessuna zona d'Italia è a rischio alto" in text


def test_payload_wraps_report() -> None:
    report = {**_REPORT, "report_it": render_national_report_it(_REPORT)}
    payload = build_report_payload(report)
    assert payload.aoi_id == "italia"
    assert payload.pipeline_version == "v1-report-daily"
    assert payload.max_level is RiskLevel.High
    assert payload.cells[0].cell_id == "it-campania|1|1"
    assert payload.summary_it == report["report_it"]
