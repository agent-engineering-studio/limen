"""Il rapporto «Regioni da monitorare» in PDF."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from limen.report.regioni_pdf import _t, rapporto_pdf


def _regione(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "aoi_id": "it-emilia-romagna",
        "nome": "Emilia-Romagna",
        "peggiore": {
            "hazard": "flood",
            "classe": "VeryHigh",
            "score": 0.8,
            "previsto": False,
            "rango": 4,
        },
        "pericoli": {"flood": {"alte": 76, "moderate": 10, "max_score": 0.8, "classe": "VeryHigh"}},
        "previsto": {
            "flood": {"score": 0.6, "classe": "High", "target_at": "2026-10-09T02:00:00+00:00"}
        },
        "comuni": [
            {
                "istat_code": "033020",
                "nome": "Ferriere",
                "hazard": "flood",
                "score": 0.8,
                "celle_alte": 3,
            }
        ],
        "allerta": {"oggi": 1, "domani": None},
        "spiegazioni": {
            "flood": {
                "testo": (
                    "Primo paragrafo con l'accento.\n\n"
                    "Secondo paragrafo: pioggia ≥ 40 mm → allagamenti."
                ),
                "modello": "quality-cloud",
                "scritta": "2026-10-07T09:54:00+00:00",
                "livello": "VeryHigh",
                "analisi": {"driver": "pluvial_rain", "attention_window_hours": 24},
            }
        },
    }
    base.update(kw)
    return base


def test_un_pdf_vero_con_tutte_le_regioni() -> None:
    pdf = rapporto_pdf(
        [
            _regione(),
            _regione(
                aoi_id="it-molise",
                nome="Molise",
                peggiore=None,
                pericoli={},
                previsto={},
                comuni=[],
                allerta=None,
                spiegazioni={},
            ),
        ],
        generato=datetime(2026, 10, 7, 15, 0, tzinfo=UTC),
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 5_000


def test_i_caratteri_fuori_tabella_si_sostituiscono_e_l_xml_si_protegge() -> None:
    assert _t("≥ 40 → <b>") == "&gt;= 40 -&gt; &lt;b&gt;"
    assert _t("è · «»") == "è · «»"
