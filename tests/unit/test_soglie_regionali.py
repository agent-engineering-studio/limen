"""Le soglie di pioggia regionali per le frane e la variante del backtest (#506)."""

from __future__ import annotations

import pytest

from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.core.scoring.soglie_regionali import Catalogo, carica, con_soglie_regionali


def test_il_file_si_legge_e_ogni_soglia_ha_una_fonte_con_licenza() -> None:
    catalogo = carica()
    assert catalogo.soglie
    for s in catalogo.soglie:
        assert catalogo.fonti[s.fonte].licenza.startswith("CC BY")
    assert set(catalogo.per_aoi()) == {
        "it-calabria",
        "it-abruzzo",
        "it-marche",
        "it-umbria",
        "it-sicilia",
    }


def test_una_soglia_e_d_diventa_intensita() -> None:
    calabria = carica().per_aoi()["it-calabria"]
    curva = calabria.in_intensita()
    assert curva.alpha == 8.6
    assert curva.beta == pytest.approx(0.59)


def test_la_variante_cambia_solo_caine_e_solo_nelle_aoi_regionali() -> None:
    prima = load_regional_thresholds()
    dopo = con_soglie_regionali(prima)

    nome = dopo.macroregion_for("it-calabria")
    assert nome == "regionale_calabria-t5"
    assert dopo.caine.macroregions[nome].beta == pytest.approx(0.59)
    assert dopo.macroregion_for("it-puglia") == prima.macroregion_for("it-puglia")
    assert dopo.macroregion_for("it-toscana") == prima.macroregion_for("it-toscana")
    # rain_floor e flood_forecast leggono la voce della macroregione di prima.
    vecchia = prima.macroregion_for("it-calabria")
    assert prima.rain_floor is not None and dopo.rain_floor is not None
    assert dopo.rain_floor.macroregions[nome] == prima.rain_floor.macroregions[vecchia]
    assert prima.flood_forecast is not None and dopo.flood_forecast is not None
    ff = prima.flood_forecast.macroregions
    assert dopo.flood_forecast.macroregions[nome] == ff.get(vecchia, ff["italy_default"])
    # La produzione non cambia: il file del pacchetto resta quello.
    assert load_regional_thresholds().macroregion_for("it-calabria") == vecchia


def test_un_aoi_con_due_soglie_regionali_non_passa() -> None:
    doppio = {
        "fonti": {"f": {"citazione": "c", "url": "u", "licenza": "CC BY 4.0"}},
        "soglie": [
            {"id": "a", "aoi": ["it-x"], "forma": "I-D", "alpha": 1.0, "beta": 0.5, "fonte": "f"},
            {"id": "b", "aoi": ["it-x"], "forma": "I-D", "alpha": 2.0, "beta": 0.5, "fonte": "f"},
        ],
    }
    with pytest.raises(ValueError, match="due soglie"):
        Catalogo.model_validate(doppio)


def test_una_forma_senza_il_suo_esponente_non_passa() -> None:
    sbagliato = {
        "fonti": {"f": {"citazione": "c", "url": "u", "licenza": "CC BY 4.0"}},
        "soglie": [
            {"id": "a", "zona": "z", "forma": "E-D", "alpha": 1.0, "beta": 0.5, "fonte": "f"}
        ],
    }
    with pytest.raises(ValueError, match="gamma"):
        Catalogo.model_validate(sbagliato)
