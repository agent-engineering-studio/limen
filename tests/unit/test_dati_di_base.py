"""Il dato di base di una cella con la sua fonte (#422): funzione pura."""

from __future__ import annotations

from limen.config.catalogo_dati import carica_catalogo
from limen.core.dati_di_base import StatoDato, dati_di_base
from limen.core.models.hazard import HazardType

CAT = carica_catalogo()


def _colonne(pericolo: HazardType) -> list[str]:
    return [
        v.misura.colonna
        for v in CAT.voci
        if v.misura.colonna is not None and pericolo in v.pericoli
    ]


def test_solo_le_voci_del_pericolo_nell_ordine_del_catalogo() -> None:
    for pericolo in HazardType:
        out = dati_di_base(CAT, pericolo, {}, {}, {})
        assert [d.colonna for d in out] == _colonne(pericolo)


def test_letture_deterministiche() -> None:
    valori = {
        "imperviousness_norm": 0.418,
        "flood_hazard_norm": 0.8,
        "slope_deg": 18.27,
        "landuse_code": "311",
        "distance_to_road_m": 1240.0,
        "litho_weight": 0.85,
        "iffi_density_500": 3.0,
        "pai_class_norm": 1.0,
    }
    classi = {"flood_hazard_norm": "P3", "litho_weight": "Argille", "pai_class_norm": "P4"}
    letture = {
        d.colonna: d.lettura for p in HazardType for d in dati_di_base(CAT, p, valori, classi, {})
    }
    assert letture["imperviousness_norm"] == "suolo impermeabilizzato al 42 %"
    assert letture["flood_hazard_norm"] == "P3 elevata"
    assert letture["slope_deg"] == "pendenza 18,3°"
    assert letture["landuse_code"] == "classe CORINE 311"
    assert letture["distance_to_road_m"] == "strada più vicina a 1,2 km"
    assert letture["litho_weight"] == "Argille (peso 0,85)"
    assert letture["iffi_density_500"] == "3 frane censite entro 500 m"
    assert letture["pai_class_norm"] == "P4 molto elevata"


def test_vuoto_non_e_zero() -> None:
    """Una colonna vuota non diventa mai zero: dice se manca in regione o se la
    cella ne è fuori."""
    caricati = {"flood_hazard_norm": True, "imperviousness_norm": False}
    out = {d.colonna: d for d in dati_di_base(CAT, HazardType.FLOOD, {}, {}, caricati)}
    fuori, assente = out["flood_hazard_norm"], out["imperviousness_norm"]
    assert fuori.stato is StatoDato.ASSENTE_QUI
    assert fuori.lettura == "fuori dalle aree a pericolosità idraulica"
    assert assente.stato is StatoDato.NON_CARICATO
    assert assente.lettura == "non caricato"
    assert fuori.valore is None and assente.valore is None


def test_la_fonte_accompagna_sempre_il_valore() -> None:
    for pericolo in HazardType:
        for d in dati_di_base(CAT, pericolo, {}, {}, {}):
            voce = CAT.voce(d.id)
            assert d.fonte == voce.fonte and d.licenza == voce.licenza
            assert d.attribuzione == voce.attribuzione
