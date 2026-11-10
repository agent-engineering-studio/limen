"""Su quanti ingredienti poggia il punteggio di una cella (#484)."""

from __future__ import annotations

from datetime import date

from limen.config.catalogo_dati import carica_catalogo
from limen.core.dati_di_base import StatoDato, completezza, dati_di_base
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    ComponentBreakdown,
    FireWeatherState,
    FloodBreakdown,
    MeteoBreakdown,
    StaticBreakdown,
    WildfireBreakdown,
    segnali_da_factors,
)

CAT = carica_catalogo()
_FWI = FireWeatherState(
    day=date(2026, 8, 1), ffmc=90.0, dmc=40.0, dc=300.0, isi=8.0, bui=60.0, fwi=25.0
)
_FRANA = ComponentBreakdown(
    s=0.4,
    m=0.3,
    e=0.0,
    f=0.0,
    h=0.0,
    static_terms=StaticBreakdown(
        susc_ispra=0.4, iffi_density=0.2, slope=0.5, pai=0.3, litho_weight=0.6
    ),
    meteo_terms=MeteoBreakdown(caine_excess=0.1, caine_norm=0.2, api_factor=0.3, soil_factor=0.4),
)


def test_segnali_per_pericolo() -> None:
    assert _FRANA.segnali() == {}
    assert WildfireBreakdown(fwi_norm=0.5, fuel=0.6, slope=0.2, fire_weather=_FWI).segnali() == {
        "fwi": True
    }
    assert WildfireBreakdown(fwi_norm=0.0, fuel=0.6, slope=0.2).segnali() == {"fwi": False}
    meta = FloodBreakdown(susceptibility=0.4, pluvial=0.3, fluvial=0.0, rain_mm=40.0)
    assert meta.segnali() == {"pioggia": True, "portata": False}
    # «Pioggia sì, fiume no» è misurato, ma su metà dei segnali.
    assert meta.measured()


def test_i_segnali_non_entrano_nei_factors() -> None:
    # La completezza si legge, non si scrive: le righe salvate non cambiano forma.
    for b in (
        _FRANA,
        WildfireBreakdown(fwi_norm=0.5, fuel=0.6, slope=0.2, fire_weather=_FWI),
        FloodBreakdown(susceptibility=0.4, pluvial=0.3, fluvial=0.0, rain_mm=40.0),
    ):
        payload = b.factors_payload()
        assert "segnali" not in payload
        assert segnali_da_factors(b.hazard_type, payload) == b.segnali()


def test_una_riga_illeggibile_non_inventa_segnali() -> None:
    assert segnali_da_factors(HazardType.FLOOD, {"s": 0.2}) == {}


def test_caricato_ma_fuori_e_un_ingrediente_noto() -> None:
    caricati = {"flood_hazard_norm": True}
    dati = dati_di_base(CAT, HazardType.FLOOD, {"imperviousness_norm": 0.4}, {}, caricati)
    stati = {d.colonna: d.stato for d in dati}
    assert stati["flood_hazard_norm"] is StatoDato.ASSENTE_QUI
    c = completezza(dati, {"pioggia": True, "portata": False})
    non_caricati = [d for d in dati if d.stato is StatoDato.NON_CARICATO]
    assert c.totali == len(dati) + 2
    assert c.presenti == c.totali - len(non_caricati) - 1
    assert "idraulica" not in c.dati_mancanti
    assert c.dati_mancanti == [d.id for d in non_caricati]
    assert c.segnali_mancanti == ["portata"]
    assert c.lettura.startswith(f"{c.presenti} ingredienti su {c.totali}; mancano: ")
    assert c.lettura.endswith("portata del fiume (GloFAS)")


def test_tutto_presente_per_ogni_pericolo() -> None:
    for pericolo in HazardType:
        colonne = [
            str(v.misura.colonna)
            for v in CAT.voci
            if v.misura.colonna is not None and pericolo in v.pericoli
        ]
        valori: dict[str, float | str | None] = dict.fromkeys(colonne, 1.0)
        dati = dati_di_base(CAT, pericolo, valori, {}, {})
        c = completezza(dati, {"x": True})
        assert (c.presenti, c.totali) == (len(colonne) + 1, len(colonne) + 1)
        assert c.lettura == f"{c.totali} ingredienti su {c.totali}, tutti presenti"
