"""Il backtest con la litologia ricalcolata dalla carta, in memoria."""

from __future__ import annotations

import pytest

from limen.cli import backtest
from limen.core.models.risk import StaticFactors


async def test_la_carta_sostituisce_solo_le_celle_che_copre(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def pesi(_aoi_id: str) -> dict[str, float]:
        return {"c1": 0.8}

    from limen.integrations.geological import sync_job

    monkeypatch.setattr(sync_job, "litho_weights_for_aoi", pesi)
    celle = [
        (StaticFactors(cell_id="c1", litho_weight=0.5, slope_deg=12.0), 16.0, 41.0),
        (StaticFactors(cell_id="c2", litho_weight=0.5), 16.1, 41.0),
    ]
    nuove = await backtest.con_litologia_della_carta("it-test", celle)
    assert [(sf.cell_id, sf.litho_weight) for sf, _, _ in nuove] == [("c1", 0.8), ("c2", 0.5)]
    # Il resto della cella resta com'era.
    assert nuove[0][0].slope_deg == 12.0 and nuove[0][1:] == (16.0, 41.0)


async def test_una_litologia_sconosciuta_ferma_il_backtest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIMEN_BACKTEST_LITOLOGIA", "inventata")
    assert await backtest.run() == 1
