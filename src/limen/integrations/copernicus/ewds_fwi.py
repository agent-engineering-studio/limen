"""L'FWI ufficiale Copernicus dall'EWDS: lo storico della catena (#280).

`cems-fire-historical-v1` è la catena FWI canadese calcolata da Copernicus su
ERA5, dal 1940 a pochi giorni fa, a 0,25°. La stessa che Limen calcola per
nodo a 0,25° da Open-Meteo (`fwi.node_spacing_deg`): messa accanto, dice se
la nostra deriva (spin-up, pioggia, ora dell'osservazione). Solo misura, non
entra nel punteggio.

Stessa API e stessa chiave del GloFAS (``COPERNICUS__EWDS_KEY``); la licenza
CC BY 4.0 del dataset va accettata una volta sulla sua pagina (lo era il
19 ottobre 2026: la richiesta di prova è passata).

Richiesta, download (consolidato, poi «intermediate») e lettura per
``long_name`` — nel NetCDF le variabili hanno nomi GRIB (``fwinx``,
``drtcode``, …) — vengono dal pacchetto `glofas-ewds`. Un nodo fuori dal
riquadro scaricato non riceve il valore del bordo: resta assente.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

from glofas_ewds import FIRE_VARIABLES, Node, Retriever, download_fire, fire_values

#: Componente di Limen → (variabile da chiedere, inizio del long_name nel file).
VARIABILI = FIRE_VARIABLES

Nodo = Node


def scarica(cartella: Path, inizio: date, fine: date, *, client: Retriever) -> list[Path]:
    """Un NetCDF per mese in ``cartella``; un mese già scaricato non si richiede."""
    return download_fire(cartella, inizio, fine, client=client)


def valori_per_nodo(
    paths: Iterable[Path], nodi: list[Nodo]
) -> dict[tuple[Nodo, date], dict[str, float]]:
    """Per (nodo, giorno) i componenti della catena; una cella senza dato non dà la riga."""
    return fire_values(paths, nodi)


__all__ = ["VARIABILI", "scarica", "valori_per_nodo"]
