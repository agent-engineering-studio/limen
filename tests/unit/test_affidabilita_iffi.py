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


def test_dove_l_inventario_e_scarso_la_frase_lo_dice() -> None:
    # Sardegna (20): 0,9 frane per km² in pericolo contro 25 in Italia.
    a = affidabilita_iffi("regioni", 20)
    assert a is not None
    assert a.inventario_scarso
    assert a.rispetto_italia is not None and a.rispetto_italia < 0.2
    assert a.frane_per_km2_pericolo is not None
    cifra = f"{a.frane_per_km2_pericolo:g}".replace(".", ",")
    assert f"Poche frane censite per il pericolo mappato in questa regione: {cifra} per km²" in (
        a.lettura
    )
    assert "può voler dire che si è rilevato poco" in a.lettura
    assert a.lettura.endswith("non sono misurate.")
    assert "Few IFFI landslides for the hazard mapped in this region" in a.lettura_en
    # Toscana (9) è vicina all'Italia: nessuna frase in più.
    b = affidabilita_iffi("regioni", 9)
    assert b is not None and not b.inventario_scarso
    assert "Poche frane" not in b.lettura and "Few IFFI" not in b.lettura_en


def test_un_comune_si_giudica_dalla_sua_provincia() -> None:
    # Cagliari (092009): il comune sta sopra l'Italia, la provincia a un ottavo.
    a = affidabilita_iffi("comuni", "092009")
    assert a is not None
    assert a.rispetto_italia is not None and a.rispetto_italia > 1
    assert a.provincia_rispetto_italia is not None and a.provincia_rispetto_italia < 0.2
    assert a.inventario_scarso
    assert "per il pericolo mappato in questa provincia" in a.lettura
    assert "mapped in this province" in a.lettura_en
    # Sarno (065135): poche frane per il pericolo del comune, ma la provincia no.
    b = affidabilita_iffi("comuni", "065135")
    assert b is not None
    assert b.rispetto_italia is not None and b.rispetto_italia < 0.2
    assert not b.inventario_scarso
    assert "Poche frane" not in b.lettura


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


def test_un_numero_vero_detto_della_cosa_sbagliata() -> None:
    # #672: 4.038 c'è nei fatti, ma sono le frane datate al giorno.
    from limen.core.grounding_idrogeo import numeri_attribuiti_male, numeri_non_trovati

    fatti = {"frane": 12000, "frane_al_giorno": 4038}
    testo = "In Puglia IFFI censisce 4.038 frane."
    assert numeri_non_trovati(testo, fatti) == []
    [m] = numeri_attribuiti_male(testo, fatti)
    assert (m.said, m.key, m.fact) == ("4.038", "frane", 12000.0)
    assert numeri_attribuiti_male("In Puglia IFFI censisce 12.000 frane.", fatti) == []
    assert numeri_attribuiti_male("Ne sono datate al giorno 4.038 frane.", fatti) == []


def test_la_lettura_iffi_non_ha_numeri_attribuiti_male() -> None:
    # Il testo che Limen stesso scrive dai fatti non deve dare falsi allarmi.
    from limen.agents.chat_agents.briefing import affidabilita_regione
    from limen.core.grounding_idrogeo import numeri_attribuiti_male

    # Puglia e Sardegna hanno anche la frase sull'inventario scarso.
    for regione in ("it-puglia", "it-liguria", "it-sicilia", "it-sardegna"):
        a = affidabilita_regione(_valutazione(regione, HazardType.LANDSLIDE))
        assert a is not None
        assert numeri_attribuiti_male(a.lettura, a.model_dump()) == []
        assert numeri_attribuiti_male(a.lettura_en, a.model_dump()) == []
        # E non è vuota per costruzione: con le cifre spostate le prende tutte e due.
        spostati = {
            **a.model_dump(),
            "frane": a.frane + 7,
            "frane_al_giorno": a.frane_al_giorno + 3,
        }
        assert {m.key for m in numeri_attribuiti_male(a.lettura, spostati)} == {
            "frane",
            "frane_al_giorno",
        }


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
