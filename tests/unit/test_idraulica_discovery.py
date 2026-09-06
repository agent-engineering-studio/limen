"""Scoperta delle tabelle del mosaico idraulico ISPRA.

Il nome della tabella nasce dal nome dello shapefile, e PostgreSQL tronca gli
identificatori a 63 byte. Sul caricamento reale la parola italiana della
severità è finita oltre il taglio:

    HPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_elevata.shp
    → mosaicatura_ispra_2020_aree_pericolosita_idraulica_hph_4c7713bb

Cercando solo «elevata» il sync tornava `flood: 0` con 85.000 poligoni già in
tabella, senza un errore — la mappa alluvione restava uniforme e non c'era
nulla da leggere per capire perché.
"""

from __future__ import annotations

from limen.integrations.geoserver_source.loader import _IDRAULICA_SEVERITY


def test_each_severity_accepts_both_the_word_and_the_directive_code() -> None:
    """La parola viene dal file sorgente, il codice dalla Direttiva Alluvioni.
    Serve accettarli entrambi: quale dei due sopravvive al troncamento dipende
    da com'è composto il nome, non da noi."""
    assert _IDRAULICA_SEVERITY == {
        "P3": ("elevata", "hph"),
        "P2": ("media", "mph"),
        "P1": ("bassa", "lph"),
    }


def test_the_real_truncated_table_names_match_exactly_one_severity() -> None:
    """I nomi veri prodotti dal caricamento su questa installazione.

    Ogni tabella deve corrispondere a una sola severità: due che ne rivendicano
    la stessa darebbero classi sovrapposte, e vincerebbe quella che capita.
    """
    reali = {
        "mosaicatura_ispra_2020_aree_pericolosita_idraulica_hph_4c7713bb": "P3",
        "mosaicatura_ispra_2020_aree_pericolosita_idraulica_mph_ad3860f0": "P2",
        "mosaicatura_ispra_2020_aree_pericolosita_idraulica_lph_a835c30c": "P1",
    }
    for tabella, atteso in reali.items():
        corrispondenti = {
            cls
            for cls, keywords in _IDRAULICA_SEVERITY.items()
            if any(k in tabella.lower() for k in keywords)
        }
        assert corrispondenti == {atteso}, f"{tabella} -> {corrispondenti}"


def test_untruncated_names_still_match() -> None:
    """Un'installazione con nomi corti non deve regredire: la parola italiana
    resta la prima scelta."""
    lunghi = {
        "pericolosita_idraulica_elevata": "P3",
        "pericolosita_idraulica_media": "P2",
        "pericolosita_idraulica_bassa": "P1",
    }
    for tabella, atteso in lunghi.items():
        corrispondenti = {
            cls
            for cls, keywords in _IDRAULICA_SEVERITY.items()
            if any(k in tabella.lower() for k in keywords)
        }
        assert corrispondenti == {atteso}, f"{tabella} -> {corrispondenti}"
