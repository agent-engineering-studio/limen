"""Il catalogo dei dati (``config/dati.yaml``, #401).

È ciò che chi installa leggerà per sapere cosa scaricare e perché: una voce
senza licenza o senza spiegazione, o una che punta a un dato inesistente,
diventa una pagina che non sa rispondere proprio alla domanda per cui esiste.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from limen.config.catalogo_dati import CatalogoDati, Livello, carica_catalogo
from limen.core.models.hazard import HazardType


def _voce(**sovrascritti: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "dtm",
        "nome": "pendenza (DTM)",
        "a_cosa_serve": "la pendenza",
        "pericoli": ["landslide"],
        "livello": "essenziale",
        "misura": {"colonna": "slope_deg"},
        "variabile": "LIMEN_DEM_RASTER",
        "fonte": "IRPI-CNR",
        "licenza": "CC-BY 4.0",
        "peso_gb": 22.1,
    }
    return base | sovrascritti


def test_il_catalogo_del_pacchetto_si_carica() -> None:
    catalogo = carica_catalogo()
    assert len(catalogo.voci) >= 10


def test_ogni_pericolo_ha_almeno_un_dato_essenziale() -> None:
    """Un pericolo senza essenziali risulterebbe «tutto presente» a vuoto."""
    catalogo = carica_catalogo()
    for pericolo in HazardType:
        assert catalogo.essenziali(pericolo), pericolo


def test_ogni_voce_dice_licenza_e_a_cosa_serve() -> None:
    for voce in carica_catalogo().voci:
        assert voce.licenza.strip(), voce.id
        assert len(voce.a_cosa_serve) > 30, voce.id


def test_le_voci_scaricate_dicono_da_dove() -> None:
    """Chi installa deve poter risalire alla fonte: un derivato no, un
    download sì."""
    for voce in carica_catalogo().voci:
        if voce.deriva_da is None:
            assert voce.url, voce.id
            assert voce.attribuzione, voce.id


@pytest.mark.parametrize(
    "voce",
    [
        _voce(licenza=""),
        _voce(a_cosa_serve="  "),
        _voce(pericoli=[]),
        _voce(livello="indispensabile"),
        _voce(misura={}),
        _voce(misura={"colonna": "slope_deg", "tabella": "x"}),
        _voce(misura={"colonna": "slope_deg; DROP TABLE aoi"}),
        _voce(misura={"tabella": "Fire-Perimeters"}),
        _voce(variabile=None),
        _voce(peso_gb=-1),
        _voce(campo_sconosciuto=1),
    ],
)
def test_una_voce_incompleta_o_ambigua_e_rifiutata(voce: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CatalogoDati.model_validate({"voci": [voce]})


def test_id_ripetuti_e_derivati_orfani_sono_rifiutati() -> None:
    with pytest.raises(ValidationError, match="ripetuti"):
        CatalogoDati.model_validate({"voci": [_voce(), _voce()]})
    with pytest.raises(ValidationError, match="inesistenti"):
        CatalogoDati.model_validate({"voci": [_voce(id="wui", variabile=None, deriva_da="corine")]})


def test_essenziali_esclude_consigliati_e_altri_pericoli() -> None:
    catalogo = CatalogoDati.model_validate(
        {
            "voci": [
                _voce(),
                _voce(id="strade", livello="consigliato"),
                _voce(id="idraulica", pericoli=["flood"]),
            ]
        }
    )
    assert [v.id for v in catalogo.essenziali(HazardType.LANDSLIDE)] == ["dtm"]
    assert catalogo.voce("strade").livello is Livello.CONSIGLIATO
