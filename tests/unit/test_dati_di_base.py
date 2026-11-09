"""Il dato di base di una cella con la sua fonte (#422): funzione pura."""

from __future__ import annotations

from limen.config.catalogo_dati import carica_catalogo
from limen.config.corine import legenda_corine
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
    assert letture["landuse_code"] == "Boschi di latifoglie (CORINE 311)"
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


#: I 44 codici del terzo livello CORINE: i 42 presenti oggi nel database e
#: 423, 522, che in Italia non compaiono alla risoluzione di 1 km (#470).
_CODICI_CORINE = [
    "111",
    "112",
    "121",
    "122",
    "123",
    "124",
    "131",
    "132",
    "133",
    "141",
    "142",
    "211",
    "212",
    "213",
    "221",
    "222",
    "223",
    "231",
    "241",
    "242",
    "243",
    "244",
    "311",
    "312",
    "313",
    "321",
    "322",
    "323",
    "324",
    "331",
    "332",
    "333",
    "334",
    "335",
    "411",
    "412",
    "421",
    "422",
    "423",
    "511",
    "512",
    "521",
    "522",
    "523",
]


def test_ogni_codice_corine_ha_un_nome_in_due_lingue() -> None:
    legenda = legenda_corine()
    assert set(legenda.classi) == set(_CODICI_CORINE)
    assert all(n.it and n.en for n in legenda.classi.values())


def test_corine_ha_il_nome_inglese_per_la_spa() -> None:
    out = {
        d.colonna: d
        for d in dati_di_base(CAT, HazardType.WILDFIRE, {"landuse_code": "312"}, {}, {})
    }
    assert out["landuse_code"].nome_classe_en == "Coniferous forest"


def test_codice_corine_sconosciuto_resta_leggibile() -> None:
    out = {
        d.colonna: d
        for d in dati_di_base(CAT, HazardType.WILDFIRE, {"landuse_code": "999"}, {}, {})
    }
    assert out["landuse_code"].lettura == "classe CORINE 999"
    assert out["landuse_code"].nome_classe_en is None
