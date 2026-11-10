"""Il riepilogo nazionale del backtest incendio (#479)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from limen.cli import backtest_wildfire as bw
from limen.core.models.risk import RiskLevel


def _m(
    aoi: str, fuochi: int, hit: float, base: float, *, far: float = 0.0, far_misurato: bool = True
) -> bw.WildfireBacktestMetrics:
    return bw.WildfireBacktestMetrics(
        aoi_id=aoi,
        truth_fires=fuochi,
        cells_warned=0,
        hits=0,
        false_alarms=0,
        misses=0,
        hit_rate=hit,
        far=far,
        mean_lead_hours=48.0,
        base_rate=base,
        report_path=None,
        carico_celle=0.05,
        far_misurato=far_misurato,
    )


def test_una_riga_per_regione_e_il_totale_pesato(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bw, "REPORTS_DIR", tmp_path)
    out = bw.write_national_report(
        [
            _m("it-sicilia", 300, 0.80, 0.40, far=0.97),
            _m("it-basilicata", 100, 0.40, 0.20, far=0.99),
            _m("it-valle-d-aosta", 0, 0.0, 0.0, far_misurato=False),
        ],
        start=date(2025, 6, 1),
        end=date(2025, 9, 30),
        alert_level=RiskLevel.High,
    )
    testo = out.read_text(encoding="utf-8")
    assert out.name == "backtest_wildfire_italia_2025-06-01_2025-09-30.md"
    assert "| `it-sicilia` | 300 | 80% | 40% | 2.00x | 5.0% | 97.0% | 48 h |" in testo
    assert "| `it-valle-d-aosta` | 0 | — | — | — | 5.0% | — | — |" in testo
    # Pesato sulle celle bruciate: (300·0,8 + 100·0,4) / 400 = 70 %, non 60 %.
    assert "| **Italia** | **400** | **70%** | **35%** | **2.00x** |" in testo
    assert "## Provenienza" in testo
    # La riga di Basilicata viene prima di Sicilia: ordine per AOI.
    assert testo.index("it-basilicata") < testo.index("it-sicilia")
