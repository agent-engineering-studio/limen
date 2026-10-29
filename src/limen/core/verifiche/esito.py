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
    if misura.get("adesso_non_misurato") and not misura.get("corse"):
        return "non_verificabile", "dato meteo mancante nelle ore prima"

    fondo = misura.get("fondo_classe_max")
    prevista = misura.get("classe_prevista_max")
    # Sopra un fondo Moderato il segnale è l'Alto, non un altro Moderato.
    if _RANGO[fondo] < _RANGO["Moderate"]:
        anticipo = misura.get("anticipo_ore_moderato")
    else:
        anticipo = misura.get("anticipo_ore_alto")
    if (
        anticipo is not None
        and anticipo >= ANTICIPO_MINIMO_ORE
        and _RANGO[prevista] > _RANGO[fondo]
    ):
        return "anticipata", f"{prevista} previsto {anticipo} h prima, sopra un fondo {fondo}"

    adesso = misura.get("adesso_classe_max")
    primo = misura.get("adesso_primo_moderato")
    if (
        _RANGO[adesso] > _RANGO[fondo]
        and primo is not None
        and datetime.fromisoformat(primo) < evento
    ):
        return "contemporanea", f"lo sweep orario era salito a {adesso} prima dell'evento"
    return "mancata", f"previsione massima {prevista}, fondo {fondo}"
