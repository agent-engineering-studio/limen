"""La piena prevista detta in periodi di ritorno: un'etichetta, non un punteggio (#522).

Il ramo fluviale divide il picco previsto della portata per il q90 del nodo
(``discharge_ratio``), e quel rapporto resta il segnale del motore: misurato
contro le soglie GloFAS dei periodi di ritorno separava allo stesso modo (AUC
0,953 contro 0,952). Ma «1,6 volte il q90 del nodo» non lo legge nessuno,
«sopra la piena da 5 anni» sì. Il picco si ricava esatto, rapporto per q90,
e si confronta con le soglie ufficiali della stessa cella GloFAS.

Puro: q90 e soglie arrivano da ``glofas_repo``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from glofas_ewds import PEAK_TOLERANCE, flood_label

#: Quanto il picco salvato della corsa può scostarsi da quello ricavato dal
#: punteggio perché il giorno valga per lui: quello di glofas-ewds.
TOLLERANZA_PICCO = PEAK_TOLERANCE


@dataclass(frozen=True, slots=True)
class Piena:
    #: Il periodo di ritorno più lungo superato (2, 5 o 20 anni); ``None``
    #: se il picco sta sotto la piena da 2 anni.
    anni: int | None
    picco_m3s: float
    soglie_m3s: dict[int, float]
    #: Il giorno del picco nella corsa GloFAS, se è la stessa del punteggio.
    giorno: date | None = None


def piena(
    rapporto: float | None,
    q90: float | None,
    soglie: dict[int, float | None],
    previsto: tuple[float, date | None] | None = None,
) -> Piena | None:
    """L'etichetta, o ``None`` se manca un pezzo: ``glofas_ewds.flood_label``.

    Senza q90 o senza la soglia da 2 anni non si può dire, e «non lo so» non è
    «sotto la piena».
    """
    found = flood_label(rapporto, q90, soglie, previsto, tolerance=TOLLERANZA_PICCO)
    if found is None:
        return None
    return Piena(
        anni=found.years, picco_m3s=found.peak, soglie_m3s=found.thresholds, giorno=found.day
    )


def lettura(p: Piena) -> str:
    """In italiano, per il riquadro della cella e per un agente via MCP."""
    quando = f", picco previsto il {p.giorno:%d/%m}" if p.giorno is not None else ""
    fonte = "soglie GloFAS, corsa di controllo" if p.giorno is not None else "soglie GloFAS"
    if p.anni is None:
        return f"Portata prevista sotto la piena da 2 anni{quando} ({fonte})."
    return f"Portata prevista sopra la piena da {p.anni} anni{quando} ({fonte})."


__all__ = ["TOLLERANZA_PICCO", "Piena", "lettura", "piena"]
