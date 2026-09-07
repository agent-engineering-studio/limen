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


# --- sezioni multi-pericolo e cascate (#58) ---------------------------------

_HAZARDS = [
    {
        "hazard": "landslide",
        "label_it": "Frana",
        "regions": [],
        "totals": {"regions": 2, "cells": 300, "high_or_above": 3, "moderate": 15},
        "top_cells": [
            {
                "cell_id": "it-campania|1|1",
                "aoi_id": "it-campania",
                "score": 0.81,
                "level": "High",
                "place": "Amalfi",
            }
        ],
    },
    {
        "hazard": "wildfire",
        "label_it": "Incendio",
        "regions": [],
        "totals": {"regions": 1, "cells": 200, "high_or_above": 0, "moderate": 40},
        "top_cells": [
            {
                "cell_id": "it-puglia|3|3",
                "aoi_id": "it-puglia",
                "score": 0.42,
                "level": "Moderate",
                "place": "Gravina",
            }
        ],
    },
]


def test_hazard_sections_name_each_hazard() -> None:
    text = render_national_report_it({**_REPORT, "hazards": _HAZARDS})
    assert "Per tipo di pericolo:" in text
    assert "· frana: 3 zone a rischio alto, 15 moderate" in text
    assert "· incendio: 40 moderate" in text
    # Il punto peggiore si nomina solo se è alto: quello dell'incendio è
    # moderato, e leggerlo accanto a un nome di paese sembrerebbe un avviso.
    assert "Amalfi" in text
    assert "Gravina" not in text


def test_hazard_sections_absent_with_a_single_hazard() -> None:
    """Con un pericolo solo la sezione ripeterebbe il paragrafo principale."""
    text = render_national_report_it({**_REPORT, "hazards": _HAZARDS[:1]})
    assert "Per tipo di pericolo" not in text
    # E il report resta quello di prima, parola per parola.
    assert text == render_national_report_it(_REPORT)


def test_cascade_section_explains_the_post_fire_effect() -> None:
    text = render_national_report_it(
        {
            **_REPORT,
            "cascades": {
                "post_fire_flood": {
                    "window_months": 18.0,
                    "cells": 12,
                    "max_multiplier": 1.58,
                    "months_since_fire_min": 3.0,
                },
                "joint_rain": {
                    "min_level": "High",
                    "window_hours": 6.0,
                    "cells": 2,
                    "top_cells": [
                        {
                            "cell_id": "it-puglia|9|9",
                            "aoi_id": "it-puglia",
                            "score": 0.7,
                            "hazards": ["flood", "landslide"],
                        }
                    ],
                },
            },
        }
    )
    assert "12 aree bruciate" in text
    assert "1.6 volte" in text
    assert "2 aree sono sopra la soglia" in text
    assert "flood e landslide" in text


def test_cascade_section_silent_when_nothing_is_firing() -> None:
    """Zero celle non è una cascata: dirlo suggerirebbe che qualcosa accade."""
    quiet = {
        "post_fire_flood": {
            "window_months": 18.0,
            "cells": 0,
            "max_multiplier": None,
            "months_since_fire_min": None,
        },
        "joint_rain": {
            "min_level": "High",
            "window_hours": 6.0,
            "cells": 0,
            "top_cells": [],
        },
    }
    text = render_national_report_it({**_REPORT, "cascades": quiet})
    assert text == render_national_report_it(_REPORT)


def test_render_tolerates_a_report_without_the_new_sections() -> None:
    """Il payload di un deployment che non ha ancora la #58 non deve rompere."""
    assert render_national_report_it(_REPORT)
