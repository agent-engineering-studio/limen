"""GloFAS dall'EWDS: la portata ordinaria dei nodi (#200) e la previsione.

Il riempimento notturno (`openmeteo/glofas_riferimenti.py`) chiede due anni di
portata nodo per nodo all'API pubblica di Open-Meteo: ~52 chiamate a nodo,
3.366 nodi, un tetto di 10.000 al giorno — tre settimane. Lo stesso dato sta
nell'Early Warning Data Store di Copernicus (`cems-glofas-historical`), che lo
serve a griglia: due anni sull'Italia sono 25 richieste mensili, e la quota di
Open-Meteo resta allo sweep.

Richieste, download, scelta della cella e lettura dei NetCDF vengono dal
pacchetto `glofas-ewds` (Apache-2.0, estratto da qui): GloFAS 4 e non 5, la
cella che Open-Meteo serve (quella dichiarata spostata di un passo a est,
28 nodi su 28 l'11 ottobre 2026), consolidato e poi «intermediate», la corsa di
controllo, il ``valid_time`` che è la fine del giorno. Qui resta ciò che è di
Limen: le credenziali dalle impostazioni, l'etichetta ``fonte`` delle righe,
la regola dei giorni minimi del riempimento da Open-Meteo e i log.

Il download è una dipendenza facoltativa (gruppo `copernicus`) e la licenza
CEMS-Floods va accettata una volta sul sito. Nel percorso orario non entra
niente: lo sweep legge le tabelle.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from glofas_ewds import (
    GLOFAS_VERSION,
    HISTORY_LATENCY_DAYS,
    Node,
    Retriever,
    cdsapi_client,
    discharge_series,
    download_forecast,
    download_history,
    forecast_peaks,
    references,
)

from limen.core.logging import get_logger
from limen.integrations.openmeteo.flood import MIN_REFERENCE_DAYS

log = get_logger(__name__)

#: L'etichetta delle righe di `glofas_riferimento` scritte da qui.
FONTE = f"ewds:{GLOFAS_VERSION}"
#: Quanti giorni indietro arriva lo storico dell'EWDS (intermediate compreso).
LATENZA_STORICO_GIORNI = HISTORY_LATENCY_DAYS

Nodo = Node


class _ConLog:
    """Un ``Retriever`` che scrive nel log ogni richiesta prima di inoltrarla.

    Il pacchetto non logga; così ogni file chiesto alla coda dell'EWDS, e il
    ripiego su «intermediate» di un mese senza consolidato, resta visibile.
    """

    def __init__(self, client: Retriever) -> None:
        self._client = client

    def retrieve(self, name: str, request: dict[str, Any], target: str) -> Any:
        prodotto = request.get("dataset_type") or request.get("product_type")
        log.info(
            "ewds.scarica",
            dataset=name,
            file=Path(target).name,
            prodotto=prodotto[0] if isinstance(prodotto, list) else prodotto,
            giorni=len(request.get("day", [])),
        )
        return self._client.retrieve(name, request, target)


def nuovo_client(url: str, key: str) -> Retriever:
    """Un client EWDS con le credenziali delle impostazioni, non dell'ambiente."""
    return _ConLog(cdsapi_client(url, key))


def scarica(cartella: Path, inizio: date, fine: date, *, client: Retriever) -> list[Path]:
    """Un NetCDF per mese in ``cartella``; un mese già scaricato non si richiede."""
    return download_history(cartella, inizio, fine, client=client)


def serie_per_nodo(
    files: Iterable[Path], nodi: list[Nodo], *, inizio: date, fine: date
) -> dict[Nodo, list[float]]:
    """La portata giornaliera della cella Open-Meteo di ogni nodo; il mascherato non entra."""
    return discharge_series(files, nodi, start=inizio, end=fine)


def riferimenti(serie: dict[Nodo, list[float]], *, percentile: float) -> dict[Nodo, float | None]:
    """Il percentile di ogni serie; ``None`` sotto ``MIN_REFERENCE_DAYS``,
    con la stessa regola del riempimento da Open-Meteo."""
    return references(serie, p=percentile, min_days=MIN_REFERENCE_DAYS)


def scarica_previsione(cartella: Path, corsa: date, *, client: Retriever) -> Path:
    """Il file della corsa ``corsa`` in ``cartella``; se c'è già, non si richiede."""
    return download_forecast(cartella, corsa, client=client)


def picchi_per_nodo(path: Path, nodi: list[Nodo]) -> dict[Nodo, float]:
    """Il massimo previsto nella cella di ogni nodo; fuori o mascherato non compare."""
    return forecast_peaks(path, nodi)


__all__ = [
    "FONTE",
    "LATENZA_STORICO_GIORNI",
    "Nodo",
    "nuovo_client",
    "picchi_per_nodo",
    "riferimenti",
    "scarica",
    "scarica_previsione",
    "serie_per_nodo",
]
