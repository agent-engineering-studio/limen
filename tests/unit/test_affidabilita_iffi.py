"""Quanto fidarsi di IFFI in un comune o in una regione (#669): solo da mostrare."""

from __future__ import annotations

from datetime import UTC, datetime

from limen.agents.chat_agents.briefing import nota_affidabilita_iffi
from limen.config.catalogo_dati import carica_catalogo
from limen.core.affidabilita_iffi import affidabilita_iffi
from limen.core.dati_di_base import dati_di_base
from limen.core.models.context import AggregateAssessment
from limen.core.models.hazard import HazardType


def test_un_comune_senza_date_lo_dice_con_i_limiti() -> None:
    # Bari (072006) nella tabella di ispra-idrogeo: 9 frane, nessuna al giorno.
    a = affidabilita_iffi("comuni", "072006")
    assert a is not None
    assert a.frane > 0
    assert a.lettura.startswith(f"In questo comune IFFI censisce {a.frane} frane")
    assert "non sono misurate" in a.lettura
    assert a.lettura_en.startswith("In this municipality IFFI maps")
    assert a.codice == "072006"
    assert "IFFI" in a.fonte and "CC BY-SA 4.0" in a.fonte
    assert len(a.non_misurato) == 4


def test_codici_sconosciuti_o_assenti_non_rispondono() -> None:
    assert affidabilita_iffi("comuni", "999999") is None
    assert affidabilita_iffi("comuni", None) is None
    assert affidabilita_iffi("comuni", "non un codice") is None


def test_una_regione_ha_la_sua_frase() -> None:
    a = affidabilita_iffi("regioni", 16)
    assert a is not None
    assert a.lettura.startswith("In questa regione IFFI censisce")


def test_accanto_al_dato_iffi_e_non_altrove() -> None:
    a = affidabilita_iffi("comuni", "072006")
    out = dati_di_base(
        carica_catalogo(),
        HazardType.LANDSLIDE,
        {"iffi_density_500": 3.0, "slope_deg": 10.0},
        {},
        {},
        a,
    )
    per_colonna = {d.colonna: d for d in out}
    assert per_colonna["iffi_density_500"].affidabilita == a
    assert per_colonna["iffi_density_500"].lettura == "3 frane censite entro 500 m"
    assert per_colonna["slope_deg"].affidabilita is None


def _valutazione(aoi_id: str, pericolo: HazardType) -> AggregateAssessment:
    return AggregateAssessment(
        aoi_id=aoi_id,
        hazard_type=pericolo,
        model_version="v1",
        valuation_time=datetime(2026, 11, 23, tzinfo=UTC),
        n_cells=1,
        cells_high_or_above=0,
        cells_by_level={"Low": 1},
        top_cells=[],
    )


def test_il_briefing_frane_riceve_l_affidabilita_della_regione() -> None:
    nota = nota_affidabilita_iffi(_valutazione("it-puglia", HazardType.LANDSLIDE))
    assert "Affidabilità dell'inventario IFFI: In questa regione IFFI censisce" in nota
    assert nota_affidabilita_iffi(_valutazione("it-puglia", HazardType.FLOOD)) == ""
    assert nota_affidabilita_iffi(_valutazione("non-una-regione", HazardType.LANDSLIDE)) == ""


def test_il_source_di_idrogeo_mcp() -> None:
    from limen.core.grounding_idrogeo import fonte

    assert fonte({"source": " ISPRA IFFI, CC BY-SA 4.0 "}) == "ISPRA IFFI, CC BY-SA 4.0"
    assert fonte({"source": 3, "idrogeo_source": "ISPRA PIR"}) == "ISPRA PIR"
    assert fonte({}) is None


def test_i_numeri_non_trovati_nei_fatti() -> None:
    from limen.core.grounding_idrogeo import numeri_non_trovati

    assert numeri_non_trovati("Bari ha 9 frane.", {"frane": 9}) == []
    assert numeri_non_trovati("Bari ha 53 frane.", {"frane": 9}) == ["53"]
    assert numeri_non_trovati("Caddero 40 mm.", {"frane": 9}, "pioggia 40 mm") == []


def test_il_briefing_frane_cita_il_source_iffi_e_controlla_i_numeri(
    caplog: object,
) -> None:
    from limen.agents.chat_agents.briefing import affidabilita_regione, con_fonte_idrogeo

    a = affidabilita_regione(_valutazione("it-puglia", HazardType.LANDSLIDE))
    assert a is not None
    testo = con_fonte_idrogeo("Un racconto senza numeri.", a, "messaggio")
    assert testo.endswith(f"**Fonti**\n- {a.fonte}")
    # Con un blocco di fonti già presente, la riga si aggiunge lì, una volta.
    con_blocco = con_fonte_idrogeo("Racconto.\n\n**Fonti**\n- Altro", a, "m")
    assert con_blocco == f"Racconto.\n\n**Fonti**\n- Altro\n- {a.fonte}"
    assert con_fonte_idrogeo(con_blocco, a, "m") == con_blocco
    # Senza affidabilità (altri pericoli) il testo non cambia.
    assert con_fonte_idrogeo("Racconto.", None, "m") == "Racconto."
