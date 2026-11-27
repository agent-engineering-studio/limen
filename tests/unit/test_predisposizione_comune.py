"""Le classi ISPRA di predisposizione del comune, dagli indicatori salvati (#672)."""

from __future__ import annotations

from limen.data.repos.esposizione_comuni_repo import predisposizione


def test_le_due_classi_dalle_quote_del_comune() -> None:
    # Bologna (037006), indicatori IdroGEO salvati il 2026-11.
    p = predisposizione({"ar_frp3p4p": 6.726, "aridp2_p": 57.704})
    assert p is not None
    assert p["frana"] == {"classe": "medium", "quota_pct": 6.726}
    assert p["alluvione"] == {"classe": "very high", "quota_pct": 57.704}
    assert "very high" in p["regola"]


def test_meno_uno_e_non_disponibile_non_zero() -> None:
    p = predisposizione({"ar_frp3p4p": 0, "aridp2_p": -1})
    assert p is not None
    assert p["frana"]["classe"] == "none"
    assert p["alluvione"] == {"classe": None, "quota_pct": None}


def test_senza_nessuna_quota_niente() -> None:
    assert predisposizione({}) is None
