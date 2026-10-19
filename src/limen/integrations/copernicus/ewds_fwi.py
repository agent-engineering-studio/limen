"""L'FWI ufficiale Copernicus dall'EWDS: lo storico della catena (#280).

`cems-fire-historical-v1` è la catena FWI canadese calcolata da Copernicus su
ERA5, dal 1940 a pochi giorni fa, a 0,25°. La stessa che Limen calcola per
nodo a 0,25° da Open-Meteo (`fwi.node_spacing_deg`): messa accanto, dice se
la nostra deriva (spin-up, pioggia, ora dell'osservazione). Solo misura, non
entra nel punteggio.

Stessa API e stessa chiave del GloFAS (``COPERNICUS__EWDS_KEY``); la licenza
CC BY 4.0 del dataset va accettata una volta sulla sua pagina (lo era il
19 ottobre 2026: la richiesta di prova è passata). I giorni recenti esistono
solo come «intermediate», come per il GloFAS.

Nel NetCDF le variabili hanno nomi brevi GRIB (``fwinx``, ``drtcode``, …):
qui si riconoscono dal ``long_name``, che è quello che la documentazione dà.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.integrations.copernicus.ewds_glofas import AREA_ITALIA, mesi

log = get_logger(__name__)

DATASET = "cems-fire-historical-v1"
VERSIONE = "4_1"
#: Il passo della griglia richiesta: il più fine che il dataset offre.
GRIGLIA = "0.25/0.25"

#: Componente di Limen → (variabile da chiedere, inizio del long_name nel file).
VARIABILI: dict[str, tuple[str, str]] = {
    "fwi": ("fire_weather_index", "forest fire weather index"),
    "ffmc": ("fine_fuel_moisture_code", "fine fuel moisture code"),
    "dmc": ("duff_moisture_code", "duff moisture code"),
    "dc": ("drought_code", "drought code"),
    "isi": ("initial_fire_spread_index", "initial fire spread index"),
    # Nel file è «Fire buildup index», non «Build up index» come nella richiesta.
    "bui": ("build_up_index", "fire buildup index"),
}

Nodo = tuple[float, float]


def richiesta(
    anno: int, mese: int, giorni: list[str], *, prodotto: str = "consolidated_dataset"
) -> dict[str, Any]:
    return {
        "product_type": "reanalysis",
        "variable": [v for v, _ in VARIABILI.values()],
        "dataset_type": prodotto,
        "system_version": [VERSIONE],
        "year": [str(anno)],
        "month": [f"{mese:02d}"],
        "day": giorni,
        "grid": GRIGLIA,
        "data_format": "netcdf",
        "area": list(AREA_ITALIA),
    }


def scarica(cartella: Path, inizio: date, fine: date, *, client: Any) -> list[Path]:
    """Un NetCDF per mese in ``cartella``; un mese già scaricato non si richiede."""
    cartella.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for anno, mese, giorni in mesi(inizio, fine):
        nome = f"cems_fire_{VERSIONE}_{anno}{mese:02d}_{giorni[0]}-{giorni[-1]}.nc"
        destinazione = cartella / nome
        if not destinazione.exists():
            parziale = destinazione.with_suffix(".part")
            log.info("ewds.fwi.scarica", file=nome, giorni=len(giorni))
            try:
                client.retrieve(DATASET, richiesta(anno, mese, giorni), str(parziale))
            except Exception as exc:
                if "valid combination" not in str(exc):
                    raise
                log.info("ewds.fwi.intermedio", file=nome)
                client.retrieve(
                    DATASET,
                    richiesta(anno, mese, giorni, prodotto="intermediate_dataset"),
                    str(parziale),
                )
            parziale.rename(destinazione)
        files.append(destinazione)
    return files


def valori_per_nodo(
    paths: Iterable[Path], nodi: list[Nodo]
) -> dict[tuple[Nodo, date], dict[str, float]]:
    """Per (nodo, giorno) i componenti della catena, dalla cella più vicina.

    Una cella senza dato (mare, bordo) non produce la riga: assente, non zero.
    """
    import netCDF4
    import numpy as np

    out: dict[tuple[Nodo, date], dict[str, float]] = {}
    for path in paths:
        with netCDF4.Dataset(path) as nc:
            lats = np.asarray(nc.variables["latitude"][:], dtype=float)
            lons = np.asarray(nc.variables["longitude"][:], dtype=float)
            tempi = nc.variables["valid_time"]
            giorni = [datetime.fromtimestamp(float(t), tz=UTC).date() for t in np.asarray(tempi[:])]
            per_nome = {
                getattr(v, "long_name", "").lower(): v
                for v in nc.variables.values()
                if v.dimensions == ("valid_time", "latitude", "longitude")
            }
            colonne: dict[str, Any] = {}
            for componente, (_, inizio_nome) in VARIABILI.items():
                for nome, v in per_nome.items():
                    if nome.startswith(inizio_nome):
                        colonne[componente] = np.ma.filled(np.ma.asarray(v[:], dtype=float), np.nan)
            for lon, lat in nodi:
                i = int(np.abs(lats - lat).argmin())
                j = int(np.abs(lons - lon).argmin())
                for t, giorno in enumerate(giorni):
                    valori = {
                        c: float(a[t, i, j]) for c, a in colonne.items() if np.isfinite(a[t, i, j])
                    }
                    if valori:
                        out[((lon, lat), giorno)] = valori
    return out


__all__ = ["DATASET", "VARIABILI", "richiesta", "scarica", "valori_per_nodo"]
