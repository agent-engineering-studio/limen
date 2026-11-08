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

import statistics
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


#: Una regione è «da verificare» quando la sua quota di celle con un valore > 0
#: sta sotto questa frazione della mediana delle regioni. Misura del 2026-11-08
#: (#467): la quota più bassa vera è IFFI in Puglia, 6,8 % contro una mediana
#: del 70 % (rapporto 0,097), e una regione caricata a zero vale 0. Il 5 % sta
#: fra le due: la Puglia, pianeggiante e con poche frane, non è un errore.
QUOTA_MINIMA_SULLA_MEDIANA = 0.05


def regioni_da_verificare(
    catalogo: CatalogoDati,
    per_regione: Mapping[str, Mapping[str, int]],
    informativi: Mapping[str, Mapping[str, int]],
    celle: Mapping[str, int],
) -> dict[str, list[str]]:
    """Per le voci ``informativo``, le regioni caricate ma quasi tutte a zero.

    Non toglie la prontezza: è un controllo di plausibilità, non una misura.
    Lo scopo è il caso Trentino (#454) — IFFI caricato, densità zero ovunque —
    che il conteggio dei valori non vede, perché zero è un valore.
    """
    out: dict[str, list[str]] = {}
    for v in catalogo.voci:
        if v.misura.informativo is None:
            continue
        quote = {
            aoi: informativi.get(aoi, {}).get(v.id, 0) / celle[aoi]
            for aoi, conte in per_regione.items()
            if conte.get(v.id, 0) > 0 and celle.get(aoi)
        }
        if not quote:
            out[v.id] = []
            continue
        mediana = statistics.median(quote.values())
        # Mediana zero: il dato è a zero quasi ovunque, e il confronto con le
        # altre regioni non regge più. Da verificare ogni regione a zero.
        soglia = QUOTA_MINIMA_SULLA_MEDIANA * mediana
        out[v.id] = sorted(aoi for aoi, q in quote.items() if q < soglia or q == 0)
    return out


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


__all__ = [
    "QUOTA_MINIMA_SULLA_MEDIANA",
    "byte_stimati",
    "mancanti",
    "regioni_da_verificare",
    "regioni_senza",
    "scaricabili",
]
