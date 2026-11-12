"""Il report di `limen glofas-ewds`: Open-Meteo contro la rianalisi EWDS (#448)."""

from __future__ import annotations

from datetime import date

from limen.cli.glofas_ewds import confronto


def test_il_confronto_conta_per_classe_e_mette_in_cima_il_nodo_piu_lontano() -> None:
    om = {(16.1, 39.2): 0.78, (11.9, 44.3): 12.49, (12.0, 44.3): 5.0, (9.0, 45.0): 150.0}
    ewds = {(16.1, 39.2): 0.24, (11.9, 44.3): 12.79, (12.0, 44.3): None, (9.0, 45.0): 151.0}

    testo = confronto(om, ewds, inizio=date(2024, 11, 7), fine=date(2026, 11, 7))

    assert "Nodi con un riferimento Open-Meteo: 4; confrontabili: 3; senza serie EWDS: 1." in testo
    tutti = next(r for r in testo.splitlines() if r.startswith("| tutti |"))
    assert tutti.split("|")[2].strip() == "3"
    assert tutti.endswith("| 33.3% |")
    assert "| ≥ 100 | 1 |" in testo
    peggiori = testo.split("## I nodi più lontani")[1]
    assert peggiori.splitlines()[4] == "| 16.10, 39.20 | 0.78 | 0.24 | 0.31 |"
