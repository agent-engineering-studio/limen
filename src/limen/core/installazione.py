"""Quanto è pronto Limen, e cosa si può scaricare (#404, epic #409).

Un pericolo è pronto quando ogni sua voce **essenziale** del catalogo c'è in
**ogni regione seminata**. Non basta che ci sia da qualche parte: un DTM
caricato per la sola Puglia darebbe «pronto» con diciannove regioni dalla
mappa uniforme, ed è la risposta rassicurante che Limen non deve mai dare
(«non misurato» non è «nessun pericolo»). Nessuna soglia percentuale: le
celle di mare restano legittimamente senza DTM o CORINE.

Le regole su cosa si può chiedere al worker stanno qui, non nella route né
nella CLI, che le traducono in un 422 o in un messaggio d'errore.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from limen.config.catalogo_dati import CatalogoDati
from limen.core.models.hazard import HazardType


def regioni_senza(
    catalogo: CatalogoDati, per_regione: Mapping[str, Mapping[str, int]]
) -> dict[str, list[str]]:
    """Per ogni voce misurata per cella, le regioni seminate che non l'hanno."""
    return {
        v.id: sorted(aoi for aoi, conte in per_regione.items() if conte.get(v.id, 0) == 0)
        for v in catalogo.voci
        if v.misura.colonna is not None
    }


def mancanti(
    catalogo: CatalogoDati,
    *,
    totali: Mapping[str, int],
    per_regione: Mapping[str, Mapping[str, int]],
) -> dict[HazardType, list[str]]:
    """Per ogni pericolo, gli id delle voci essenziali che mancano.

    Una voce per cella manca se manca in almeno una regione; una voce a
    tabella se la tabella è vuota. Senza regioni seminate manca tutto: un
    database vuoto non è «pronto» a vuoto.
    """
    senza = regioni_senza(catalogo, per_regione)

    def manca(id_: str) -> bool:
        if not per_regione:
            return True
        if id_ in senza:
            return bool(senza[id_])
        return totali.get(id_, 0) == 0

    return {h: [v.id for v in catalogo.essenziali(h) if manca(v.id)] for h in HazardType}


def scaricabili(catalogo: CatalogoDati, voci: Sequence[str]) -> list[str]:
    """Le voci richieste, se si possono scaricare; ``ValueError`` altrimenti."""
    note = {v.id: v for v in catalogo.voci}
    for voce in voci:
        if voce not in note:
            raise ValueError(f"Voce sconosciuta: {voce}.")
        if note[voce].deriva_da is not None:
            raise ValueError(
                f"{note[voce].nome} non si scarica: Limen lo calcola da un altro dato."
            )
    return list(voci)


def byte_stimati(catalogo: CatalogoDati) -> dict[str, int]:
    """Il peso del catalogo in byte, per le voci che ne hanno uno."""
    return {v.id: round(v.peso_gb * 1e9) for v in catalogo.voci if v.peso_gb > 0}


__all__ = ["byte_stimati", "mancanti", "regioni_senza", "scaricabili"]
