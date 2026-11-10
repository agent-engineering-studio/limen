"""Il catalogo degli eventi MCP, i cursori e i payload (#371)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from limen.core import eventi
from limen.core.eventi import ArgomentiNonValidiError, Posizione


def test_il_catalogo_offre_solo_il_poll_e_tre_eventi() -> None:
    nomi = [e["name"] for e in eventi.catalogo()]
    assert nomi == [eventi.ALLERTA, eventi.CAMBIO_CLASSE, eventi.NON_MISURATO]
    assert all(e["delivery"] == ["poll"] for e in eventi.catalogo())


def test_il_cursore_fa_il_giro_ed_e_opaco() -> None:
    p = Posizione(t=datetime(2026, 11, 10, 12, tzinfo=UTC), id=42)
    testo = eventi.codifica(p)
    assert "42" not in testo
    assert eventi.decodifica(testo) == p
    with pytest.raises(ArgomentiNonValidiError):
        eventi.decodifica("non-un-cursore")


@pytest.mark.parametrize(
    ("nome", "argomenti"),
    [
        (eventi.ALLERTA, {"hazard": "meteorite"}),
        (eventi.CAMBIO_CLASSE, {"min_level": "None"}),
        (eventi.NON_MISURATO, {"min_level": "High"}),
        (eventi.ALLERTA, {"colore": "rosso"}),
    ],
)
def test_argomenti_fuori_schema_si_rifiutano(nome: str, argomenti: dict[str, Any]) -> None:
    with pytest.raises(ArgomentiNonValidiError):
        eventi.filtro(nome, argomenti)


def test_i_livelli_predefiniti_sono_quelli_dello_schema() -> None:
    assert eventi.filtro(eventi.ALLERTA, None).livello_minimo == "Moderate"
    assert eventi.filtro(eventi.CAMBIO_CLASSE, {}).livello_minimo == "High"
    assert eventi.livelli_da("High") == ["High", "VeryHigh"]


def test_l_alluvione_porta_l_attribuzione_e_tutti_l_avvertenza() -> None:
    riga = {
        "id": 7,
        "cell_id": "c",
        "aoi_id": "it-x",
        "hazard": "flood",
        "classe": "High",
        "prima": "Moderate",
        "score": 0.7,
        "measured": True,
    }
    dati = eventi.payload(riga, eventi.CAMBIO_CLASSE, 2026)
    assert dati["attribuzione"] == (
        "Contains modified Copernicus Emergency Management Service information, 2026"
    )
    assert "non un'allerta ufficiale" in dati["avvertenza"]
    assert (dati["from"], dati["to"]) == ("Moderate", "High")
    frana = eventi.payload({**riga, "hazard": "landslide"}, eventi.NON_MISURATO, 2026)
    assert frana["attribuzione"] is None
    assert eventi.id_evento(eventi.CAMBIO_CLASSE, riga) == "class:7"
