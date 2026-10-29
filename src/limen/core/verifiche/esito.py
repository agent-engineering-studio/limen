"""L'esito di una verifica dalla misura di ``anticipo.sql``: le regole del §5
della skill ``limen-fact-check``, in codice, perché la raccolta quotidiana e
il fact check a mano decidano allo stesso modo.

Il fondo è il punto: dove un comune sta in Moderato tutti i giorni, una
previsione Moderata è lo sfondo e non un segnale (Melito, 10 ottobre 2026: 71
ore di «anticipo» che erano solo il terreno).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

_RANGO = {None: 0, "None": 0, "Low": 1, "Moderate": 2, "High": 3, "VeryHigh": 4}
#: Sotto queste ore un'allerta non dà il tempo di fare niente.
ANTICIPO_MINIMO_ORE = 6
#: Il fondo di `anticipo.sql` parte 10 giorni prima dell'evento: con uno
#: storico più corto la classe di fondo è letta su un pezzo solo, e un fondo
#: sottostimato fa passare per anticipo lo sfondo.
INIZIO_FONDO = timedelta(days=10)


def anticipo_sopra_fondo(misura: dict[str, Any]) -> tuple[float, str] | None:
    """Le ore fra la prima corsa con una classe **sopra** il fondo e
    l'evento, e la classe più alta fra quelle corse; ``None`` se nessuna lo
    supera, in ore non arrotondate (si arrotonda solo per mostrarle). È
    l'anticipo che conta: con un fondo Alto, un Alto previsto 72 h
    prima e un Molto alto arrivato 20 h prima sono un anticipo di 20 ore, non
    di 72 — ``anticipo_ore_moderato`` e ``_alto`` restano le soglie grezze."""
    fondo = misura.get("fondo_classe_max")
    sopra = [c for c in misura.get("corse") or [] if _RANGO.get(c.get("classe"), 0) > _RANGO[fondo]]
    if not sopra:
        return None
    evento = datetime.fromisoformat(misura["evento"])
    prima = min(datetime.fromisoformat(c["run_at"]) for c in sopra)
    classe = max((c["classe"] for c in sopra), key=lambda k: _RANGO[k])
    return (evento - prima).total_seconds() / 3600, classe


def esito(misura: dict[str, Any]) -> tuple[str, str]:
    """``(esito, motivo)``: ``non_verificabile``, ``anticipata``,
    ``contemporanea`` o ``mancata``, nell'ordine del §5."""
    evento = datetime.fromisoformat(misura["evento"])
    storico = misura.get("storico_dal")
    if storico is None or datetime.fromisoformat(storico) > evento:
        return "non_verificabile", "evento prima dello storico delle previsioni"
    if datetime.fromisoformat(storico) > evento - INIZIO_FONDO:
        return "non_verificabile", "il fondo dei giorni prima non è più nello storico"
    if not misura.get("celle"):
        return "non_verificabile", "comune senza celle valutate"
    # `is False`: una misura congelata prima che la query lo dicesse non ha la
    # chiave, e non si declassa.
    if misura.get("pericolo_valutato") is False:
        return "non_verificabile", "il pericolo non è stato valutato nei giorni prima"
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
    sopra = anticipo_sopra_fondo(misura)
    if sopra is not None and sopra[0] >= ANTICIPO_MINIMO_ORE:
        ore, classe = sopra
        return "anticipata", f"{classe} previsto {ore:.0f} h prima, sopra un fondo {fondo}"

    adesso = misura.get("adesso_classe_max")
    primo = misura.get("adesso_primo_moderato")
    if (
        _RANGO[adesso] > _RANGO[fondo]
        and primo is not None
        and datetime.fromisoformat(primo) < evento
    ):
        return "contemporanea", f"lo sweep orario era salito a {adesso} prima dell'evento"
    return "mancata", f"previsione massima {prevista}, fondo {fondo}"
