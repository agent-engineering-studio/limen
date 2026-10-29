"""L'esito di una verifica dalla misura di ``anticipo.sql``: le regole del §5
della skill ``limen-fact-check``, in codice, perché la raccolta quotidiana e
il fact check a mano decidano allo stesso modo.

Il fondo è il punto: dove un comune sta in Moderato tutti i giorni, una
previsione Moderata è lo sfondo e non un segnale (Melito, 10 ottobre 2026: 71
ore di «anticipo» che erano solo il terreno).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

_RANGO = {None: 0, "None": 0, "Low": 1, "Moderate": 2, "High": 3, "VeryHigh": 4}
#: Sotto queste ore un'allerta non dà il tempo di fare niente.
ANTICIPO_MINIMO_ORE = 6


def esito(misura: dict[str, Any]) -> tuple[str, str]:
    """``(esito, motivo)``: ``non_verificabile``, ``anticipata``,
    ``contemporanea`` o ``mancata``, nell'ordine del §5."""
    evento = datetime.fromisoformat(misura["evento"])
    storico = misura.get("storico_dal")
    if storico is None or datetime.fromisoformat(storico) > evento:
        return "non_verificabile", "evento prima dello storico delle previsioni"
    if not misura.get("celle"):
        return "non_verificabile", "comune senza celle valutate"
    # Un buco del dato meteo rende l'evento non verificabile solo se non c'è
    # nient'altro: né una corsa sopra soglia, né un'ora misurata dello sweep.
    if (
        misura.get("adesso_non_misurato")
        and not misura.get("adesso_misurato")
        and not misura.get("corse")
    ):
        return "non_verificabile", "dato meteo mancante nelle ore prima"

    fondo = misura.get("fondo_classe_max")
    prevista = misura.get("classe_prevista_max")
    # L'anticipo si conta dalla prima corsa *sopra* il fondo, non da una che
    # lo eguagliava: con un fondo Alto, un Alto previsto 72 h prima e un Molto
    # alto arrivato 2 h prima non sono un anticipo di 72 ore.
    sopra = [c for c in misura.get("corse") or [] if _RANGO.get(c.get("classe"), 0) > _RANGO[fondo]]
    if sopra:
        prima = min(datetime.fromisoformat(c["run_at"]) for c in sopra)
        anticipo = round((evento - prima).total_seconds() / 3600)
        if anticipo >= ANTICIPO_MINIMO_ORE:
            classe = max((c["classe"] for c in sopra), key=lambda k: _RANGO[k])
            return "anticipata", f"{classe} previsto {anticipo} h prima, sopra un fondo {fondo}"

    adesso = misura.get("adesso_classe_max")
    primo = misura.get("adesso_primo_moderato")
    if (
        _RANGO[adesso] > _RANGO[fondo]
        and primo is not None
        and datetime.fromisoformat(primo) < evento
    ):
        return "contemporanea", f"lo sweep orario era salito a {adesso} prima dell'evento"
    return "mancata", f"previsione massima {prevista}, fondo {fondo}"
