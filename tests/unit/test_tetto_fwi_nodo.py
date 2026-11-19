"""Il FWI «pieno» di ogni nodo dalla sua climatologia estiva (#476), spento finché non misurato."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from limen.core.features.assembler import assemble_bundles
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    FireWeatherState,
    StaticFactors,
)
from limen.core.scoring.regional_thresholds import (
    TettoPerNodoBlock,
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.core.scoring.wildfire import WildfireScoringEngine
from limen.core.scoring.wildfire.climatology import LIVELLI, tetto_del_nodo

_BLOCCO = TettoPerNodoBlock(quantile=95, mesi=(6, 7, 8, 9), minimo=35.0)


def _soglie(blocco: TettoPerNodoBlock | None) -> WildfireThresholds:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return t.model_copy(update={"fwi": t.fwi.model_copy(update={"tetto_per_nodo": blocco})})


def _q(p95: float) -> list[float]:
    return [p95 if livello == 95 else 0.0 for livello in LIVELLI]


def _bundle(fwi: float, tetto: float | None) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="it-lombardia",
        cell_id="c",
        static=StaticFactors(cell_id="c", landuse_code="311", slope_deg=10.0),
        dynamic=DynamicInputs(
            valuation_time=dt.datetime(2026, 7, 15, 12, tzinfo=dt.UTC),
            fire_weather=FireWeatherState(
                day=dt.date(2026, 7, 15),
                ffmc=90,
                dmc=50,
                dc=300,
                isi=8,
                bui=70,
                fwi=fwi,
                chain_days=90,
            ),
            fwi_normalisation_max=tetto,
        ),
    )


def test_il_tetto_e_la_media_estiva_del_quantile_fra_minimo_e_massimo() -> None:
    nord = {6: _q(28.0), 7: _q(40.0), 8: _q(42.0), 9: _q(30.0)}
    assert tetto_del_nodo(nord, _BLOCCO, 50.0) == pytest.approx(35.0)  # media 35
    freddo = {7: _q(20.0)}
    assert tetto_del_nodo(freddo, _BLOCCO, 50.0) == 35.0  # mai sotto il minimo
    sud = {7: _q(64.0), 8: _q(70.0)}
    assert tetto_del_nodo(sud, _BLOCCO, 50.0) == 50.0  # al Sud non cambia niente
    assert tetto_del_nodo({1: _q(10.0)}, _BLOCCO, 50.0) is None  # nessun mese estivo


def test_spento_il_tetto_del_nodo_non_conta_e_i_factors_restano_quelli_di_prima() -> None:
    motore = WildfireScoringEngine(_soglie(None))
    senza = motore.score(_bundle(30.0, None))
    con = motore.score(_bundle(30.0, 35.0))
    assert senza.score == con.score
    assert "fwi_normalisation_max" not in con.breakdown.factors_payload()


def test_acceso_un_fwi_di_30_al_nord_pesa_come_al_sud_un_fwi_piu_alto() -> None:
    motore = WildfireScoringEngine(_soglie(_BLOCCO))
    nord = motore.score(_bundle(30.0, 35.0))
    pieno = motore.score(_bundle(30.0, None))
    assert nord.breakdown.fwi_norm == pytest.approx(30.0 / 35.0)
    assert pieno.breakdown.fwi_norm == pytest.approx(30.0 / 50.0)
    assert nord.score > pieno.score
    assert nord.breakdown.factors_payload()["fwi_normalisation_max"] == 35.0


def test_in_produzione_il_tetto_per_nodo_e_spento() -> None:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    assert t.fwi.tetto_per_nodo is None


def test_lo_yaml_rifiuta_un_quantile_che_la_tabella_non_ha() -> None:
    with pytest.raises(ValueError, match="quantile"):
        TettoPerNodoBlock(quantile=97, mesi=(7,), minimo=35.0)
    with pytest.raises(ValueError, match="mesi"):
        TettoPerNodoBlock(quantile=95, mesi=(13,), minimo=35.0)


def test_il_tetto_arriva_alla_cella_dal_suo_nodo() -> None:
    fw = FireWeatherState(
        day=dt.date(2026, 7, 15), ffmc=90, dmc=50, dc=300, isi=8, bui=70, fwi=30, chain_days=90
    )
    ctx: Any = MonitoringContext(
        aoi_id="aoi",
        hazard_type=HazardType.WILDFIRE,
        valuation_time=dt.datetime(2026, 7, 15, 12, tzinfo=dt.UTC),
        cell_ids=("a", "b"),
        cell_centroids={"a": (9.0, 45.5), "b": (15.0, 38.0)},
        fwi_nodes=((9.0, 45.5), (15.0, 38.0)),
        fwi_by_node=(fw, fw.model_copy(update={"fwi": 60})),
        fwi_tetto_by_node=(35.0, None),
    )
    dyn = {b.cell_id: b.dynamic for b in assemble_bundles(ctx)}
    assert dyn["a"].fwi_normalisation_max == 35.0
    assert dyn["b"].fwi_normalisation_max is None


def test_il_backtest_legge_il_tetto_dalla_variabile() -> None:
    from limen.cli.backtest_wildfire import leggi_tetto

    assert leggi_tetto("95:35:6-9") == _BLOCCO
    with pytest.raises(ValueError):
        leggi_tetto("95-35")
