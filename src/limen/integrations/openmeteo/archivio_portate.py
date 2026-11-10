"""Le portate GloFAS storiche per nodo, salvate su disco una volta (#478).

`backtest-flood` chiede due anni di portata giornaliera per ogni nodo (il
riferimento fluviale è un percentile pluriennale, #108) all'API pubblica di
Open-Meteo, l'unica che serve GloFAS: non si può ospitare. È la stessa quota
dello sweep, e un 429 la sospende fino a mezzanotte: l'8 novembre 2026 il
backtest della #420 è uscito con il ramo fluviale vuoto in tutte e tre le
varianti, cioè una misura della sola pioggia.

Qui ogni nodo ha un file JSON con l'arco che copre e la serie. Il passato non
cambia, quindi un nodo letto una volta non si richiede più; una prova
interrotta riprende dai nodi che mancano. **Una risposta vuota non si scrive
mai**: un degrado salvato terrebbe il nodo a secco per sempre.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from limen.config.percorsi import radice_dati


def cartella() -> Path:
    return radice_dati() / "archivio" / "glofas"


@dataclass(frozen=True, slots=True)
class SerieNodo:
    dal: date
    al: date
    portate: dict[date, float]

    def copre(self, dal: date, al: date) -> bool:
        return self.dal <= dal and self.al >= al


def _file(base: Path, nodo: tuple[float, float]) -> Path:
    lon, lat = nodo
    return base / f"{lon:.4f}_{lat:.4f}.json"


def leggi(base: Path, nodo: tuple[float, float]) -> SerieNodo | None:
    f = _file(base, nodo)
    if not f.is_file():
        return None
    dati = json.loads(f.read_text(encoding="utf-8"))
    return SerieNodo(
        dal=date.fromisoformat(dati["dal"]),
        al=date.fromisoformat(dati["al"]),
        portate={date.fromisoformat(k): float(v) for k, v in dati["portate"].items()},
    )


def scrivi(base: Path, nodo: tuple[float, float], serie: SerieNodo) -> bool:
    """Salva la serie se ha almeno un valore; dice se l'ha salvata."""
    if not serie.portate:
        return False
    base.mkdir(parents=True, exist_ok=True)
    f = _file(base, nodo)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "dal": serie.dal.isoformat(),
                "al": serie.al.isoformat(),
                "portate": {d.isoformat(): v for d, v in sorted(serie.portate.items())},
            }
        ),
        encoding="utf-8",
    )
    tmp.replace(f)
    return True


__all__ = ["SerieNodo", "cartella", "leggi", "scrivi"]
