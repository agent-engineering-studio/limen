"""La climatologia per nodo dell'innesco `cumulata` (#243)."""

from __future__ import annotations

import numpy as np
import pytest

from limen.cli.backtest import con_riferimento
from limen.cli.clima_pioggia import clima_api, quantile_cumulata, riferimenti_aoi, riferimenti_api
from limen.core.models.risk import StaticFactors


def test_il_quantile_e_della_cumulata_non_dell_ora() -> None:
    anno = np.zeros(24 * 10)
    anno[100:124] = 2.0  # un giorno da 48 mm in 24 ore
    assert quantile_cumulata([anno], ore=24, quantile=1.0) == pytest.approx(48.0, abs=12.0)
    assert quantile_cumulata([anno], ore=1, quantile=1.0) == pytest.approx(2.0)


def test_la_finestra_non_scavalca_due_anni() -> None:
    fine = np.zeros(48)
    fine[-6:] = 4.0
    inizio = np.zeros(48)
    inizio[:6] = 4.0
    # Cumulati insieme farebbero 48 mm; anno per anno restano 24.
    assert quantile_cumulata([fine, inizio], ore=24, quantile=1.0) <= 24.0


def test_nodo_asciutto_o_vuoto_non_ha_riferimento() -> None:
    assert quantile_cumulata([np.zeros(24 * 30)], ore=24, quantile=0.999) is None
    assert quantile_cumulata([np.zeros(5)], ore=24, quantile=0.999) is None


def test_i_riferimenti_valgono_solo_per_la_stessa_finestra() -> None:
    clima = {"ore": 24, "quantile": 0.999, "aoi": {"it-x": [[16.0, 40.0, 50.0]]}}
    assert riferimenti_aoi(clima, "it-x", ore=24) == [(16.0, 40.0, 50.0)]
    assert riferimenti_aoi(clima, "it-x", ore=48) is None
    assert riferimenti_aoi(clima, "it-y", ore=24) is None


def test_ogni_cella_prende_il_nodo_piu_vicino() -> None:
    celle = [(StaticFactors(cell_id="a"), 16.01, 40.0), (StaticFactors(cell_id="b"), 16.09, 40.0)]
    out = con_riferimento(celle, [(16.0, 40.0, 30.0), (16.1, 40.0, None)])
    assert [sf.pioggia_riferimento_mm for sf, _, _ in out] == [30.0, None]


def test_un_anno_non_scaricato_non_diventa_un_riferimento() -> None:
    import asyncio
    from datetime import timedelta

    from limen.cli.clima_pioggia import clima_aoi
    from limen.core.models.risk import RainfallSample

    class _Client:
        async def get_rainfall_grid(self, *, nodes, window_start, window_end, batch_size):  # type: ignore[no-untyped-def]
            if window_start.year == 2001:
                return [[] for _ in nodes]
            return [
                [
                    RainfallSample(
                        timestamp=window_start + timedelta(hours=h), precipitation_mm=1.0
                    )
                    for h in range(48)
                ]
                for _ in nodes
            ]

    def gira(anni: range):  # type: ignore[no-untyped-def]
        return asyncio.run(
            clima_aoi(
                aoi_id="x",
                bbox=(10.0, 44.0, 10.15, 44.1),
                anni=anni,
                ore=24,
                quantile=0.999,
                giorni_api=1,
                client=_Client(),  # type: ignore[arg-type]
            )
        )

    assert gira(range(2000, 2001)) is not None
    assert gira(range(2000, 2002)) is None


def test_la_pioggia_antecedente_ha_media_e_sigma_per_mese_e_scavalca_il_capodanno() -> None:
    # Due anni contigui: 1 mm/h a dicembre del primo, asciutto il resto.
    def anno(y: int, dicembre: float) -> np.ndarray:
        ore = (366 if y % 4 == 0 else 365) * 24
        h = np.zeros(ore)
        h[(ore // 24 - 31) * 24 :] = dicembre
        return h

    mesi = clima_api([anno(2001, 1.0), anno(2002, 0.0)], primo_anno=2001, giorni=30)
    gennaio, dicembre = mesi[0], mesi[11]
    assert gennaio is not None and dicembre is not None
    # Gennaio 2001 ha meno di 30 giorni alle spalle e non conta; gennaio
    # 2002 sì, e si porta dietro il dicembre bagnato.
    assert gennaio[0] > 0
    assert dicembre[1] > 0
    assert mesi[6] == (0.0, 0.0)


def test_i_riferimenti_mensili_si_leggono_solo_con_la_stessa_finestra() -> None:
    clima = {"api_giorni": 30, "api": {"x": [[10.0, 44.0, [[50.0, 20.0]] + [None] * 11]]}}
    assert riferimenti_api(clima, "x", giorni=30) == [(10.0, 44.0, ((50.0, 20.0),) + (None,) * 11)]
    assert riferimenti_api(clima, "x", giorni=20) is None
    assert riferimenti_api(clima, "y", giorni=30) is None
