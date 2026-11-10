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


@dataclass(frozen=True, slots=True)
class Piena:
    #: Il periodo di ritorno più lungo superato (2, 5 o 20 anni); ``None``
    #: se il picco sta sotto la piena da 2 anni.
    anni: int | None
    picco_m3s: float
    soglie_m3s: dict[int, float]


def piena(
    rapporto: float | None, q90: float | None, soglie: dict[int, float | None]
) -> Piena | None:
    """L'etichetta, o ``None`` se manca un pezzo: senza q90 o senza la soglia
    da 2 anni non si può dire, e «non lo so» non è «sotto la piena»."""
    if rapporto is None or q90 is None or q90 <= 0:
        return None
    note = {anni: s for anni, s in soglie.items() if s is not None and s > 0}
    if 2 not in note:
        return None
    picco = rapporto * q90
    superati = [anni for anni, s in note.items() if picco >= s]
    return Piena(anni=max(superati) if superati else None, picco_m3s=picco, soglie_m3s=note)


def lettura(p: Piena) -> str:
    """In italiano, per il riquadro della cella e per un agente via MCP."""
    if p.anni is None:
        return "Portata prevista sotto la piena da 2 anni (soglie GloFAS)."
    return f"Portata prevista sopra la piena da {p.anni} anni (soglie GloFAS)."


__all__ = ["Piena", "lettura", "piena"]
