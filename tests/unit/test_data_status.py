"""Coerenza interna del rapporto sui dati (`limen data-status`).

Il comando è una tabella di costanti che descrive lo schema. Una costante che
si scolla dallo schema produce un errore SQL al primo uso, o — peggio — un
pericolo che risulta "tutto presente" perché il layer mancante non è più
nominato da nessuna parte.
"""

from __future__ import annotations

from limen.cli.data_status import HAZARD_NEEDS, LAYERS


def test_every_hazard_need_names_a_declared_layer() -> None:
    """Un refuso qui renderebbe un pericolo silenziosamente soddisfatto."""
    declared = {layer.column for layer in LAYERS}
    for hazard, needed in HAZARD_NEEDS.items():
        missing = set(needed) - declared
        assert not missing, f"{hazard} cita layer non dichiarati: {missing}"


def test_every_layer_is_either_gated_or_derived() -> None:
    """Un layer senza gate né sorgente derivata non si saprebbe come caricare,
    e il rapporto lascerebbe l'utente senza il prossimo passo."""
    for layer in LAYERS:
        assert layer.gate or layer.derived_from, layer.column


def test_the_three_hazards_are_all_covered() -> None:
    """Aggiungere un pericolo senza dire di cosa ha bisogno lo lascerebbe
    fuori dal rapporto proprio mentre lo si sta mettendo in produzione."""
    from limen.core.models.hazard import HazardType

    italiano = {"landslide": "frana", "wildfire": "incendio", "flood": "alluvione"}
    for hazard in HazardType:
        assert italiano[hazard.value] in HAZARD_NEEDS
