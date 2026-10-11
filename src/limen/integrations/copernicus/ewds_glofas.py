"""La portata ordinaria dei nodi GloFAS, dallo storico dell'EWDS (#200).

Il riempimento notturno (`openmeteo/glofas_riferimenti.py`) chiede due anni di
portata nodo per nodo all'API pubblica di Open-Meteo: ~52 chiamate a nodo,
3.366 nodi, un tetto di 10.000 al giorno — tre settimane. Lo stesso dato sta
nell'Early Warning Data Store di Copernicus (`cems-glofas-historical`), che lo
serve a griglia: due anni sull'Italia sono 25 richieste mensili, e la quota di
Open-Meteo resta allo sweep.

Due condizioni perché il riferimento valga quanto quello di Open-Meteo:

* **la stessa versione del modello**: Open-Meteo serve la previsione con
  GloFAS 4 (verificato l'11 ottobre 2026 a Faenza: 7,1 / 6,1 / 8,9 m³/s
  dall'EWDS contro 7,3 / 5,9 / 8,9 da Open-Meteo, mentre la versione 5 dà
  circa la metà). Un rapporto fra previsione v4 e riferimento v5 sarebbe un
  numero senza significato;
* **la stessa cella**: i nodi di Limen stanno a 0,1° e molti cadono sul bordo
  fra due celle GloFAS da 0,05°. Open-Meteo sceglie la cella in float32,
  arrotondando lontano da zero da un'origine a -59,975 / -180,025
  (`cella_open_meteo`, verificata su 30 nodi veri su 30). Prendere la vicina
  sbagliata, lungo un fiume, cambia la portata di un ordine di grandezza.

Il download è una dipendenza facoltativa (gruppo `copernicus`): `cdsapi` legge
`CDSAPI_URL` / `CDSAPI_KEY` dall'ambiente, e la licenza CEMS-Floods va
accettata una volta sul sito. Nel percorso orario non entra niente.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.integrations.openmeteo.flood import MIN_REFERENCE_DAYS, percentile_of

log = get_logger(__name__)

DATASET = "cems-glofas-historical"
#: La versione che Open-Meteo usa per la previsione: cambiarla qui senza che
#: cambi là rende i rapporti incomparabili.
VERSIONE = "version_4_0"
FONTE = f"ewds:{VERSIONE}"
#: Nord, ovest, sud, est: l'Italia con mezzo grado di margine.
AREA_ITALIA = (47.6, 6.0, 35.0, 19.0)
_VARIABILE_NC = "avg_dis"
_PASSO = 0.05
_ORIGINE_LAT = -59.975
_ORIGINE_LON = -180.025

Nodo = tuple[float, float]


def _arrotonda_via_da_zero(x: float) -> int:
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def cella_open_meteo(lon: float, lat: float) -> Nodo:
    """La cella GloFAS (lon, lat) che Open-Meteo legge per un punto."""
    import numpy as np

    f = np.float32

    def asse(v: float, origine: float) -> float:
        i = _arrotonda_via_da_zero(float((f(v) - f(origine)) / f(_PASSO)))
        return round(float(f(origine) + f(i) * f(_PASSO)), 3)

    return asse(lon, _ORIGINE_LON), asse(lat, _ORIGINE_LAT)


def mesi(inizio: date, fine: date) -> list[tuple[int, int, list[str]]]:
    """I mesi fra ``inizio`` e ``fine`` (inclusi), con i giorni da chiedere."""
    out: list[tuple[int, int, list[str]]] = []
    giorno = inizio
    while giorno <= fine:
        anno, mese = giorno.year, giorno.month
        giorni: list[str] = []
        while giorno <= fine and giorno.month == mese:
            giorni.append(f"{giorno.day:02d}")
            giorno += timedelta(days=1)
        out.append((anno, mese, giorni))
    return out


def richiesta(anno: int, mese: int, giorni: list[str]) -> dict[str, Any]:
    return {
        "system_version": [VERSIONE],
        "hydrological_model": ["lisflood"],
        "product_type": ["consolidated"],
        "variable": ["average_river_discharge_in_the_last_24_hours"],
        "year": [str(anno)],
        "month": [f"{mese:02d}"],
        "day": giorni,
        "timespan": ["time_mean"],
        "area": list(AREA_ITALIA),
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def scarica(cartella: Path, inizio: date, fine: date, *, client: Any = None) -> list[Path]:
    """Un file NetCDF per mese in ``cartella``. Rilanciabile: un mese già
    scaricato per intero non si richiede.

    Il nome porta i giorni chiesti: il mese di bordo della finestra cambia ogni
    giorno, e un file parziale di ieri non deve passare per completo oggi.
    """
    cartella.mkdir(parents=True, exist_ok=True)
    if client is None:
        import cdsapi

        client = cdsapi.Client(quiet=True, progress=False)
    files: list[Path] = []
    for anno, mese, giorni in mesi(inizio, fine):
        nome = f"glofas_{VERSIONE}_{anno}{mese:02d}_{giorni[0]}-{giorni[-1]}.nc"
        destinazione = cartella / nome
        if not destinazione.exists():
            parziale = destinazione.with_suffix(".part")
            log.info("ewds.glofas.scarica", file=nome, giorni=len(giorni))
            client.retrieve(DATASET, richiesta(anno, mese, giorni), str(parziale))
            parziale.rename(destinazione)
        files.append(destinazione)
    return files


def serie_per_nodo(
    files: Iterable[Path], nodi: list[Nodo], *, inizio: date, fine: date
) -> dict[Nodo, list[float]]:
    """La portata giornaliera della cella di ogni nodo, fra ``inizio`` e ``fine``.

    Un valore mascherato (mare, cella senza rete fluviale) non entra: un nodo
    che resta con pochi giorni non avrà un riferimento, come con Open-Meteo.
    Il ``valid_time`` dell'EWDS è la fine delle 24 ore mediate, cioè il giorno
    dopo quello chiesto.
    """
    import netCDF4
    import numpy as np

    celle = [cella_open_meteo(lon, lat) for lon, lat in nodi]
    serie: dict[Nodo, list[float]] = {n: [] for n in nodi}
    for path in files:
        with netCDF4.Dataset(path) as ds:
            lats = np.asarray(ds.variables["latitude"][:], dtype=float)
            lons = np.asarray(ds.variables["longitude"][:], dtype=float)
            tempo = ds.variables["valid_time"]
            # Uno scalare per un file di un giorno, un array altrimenti.
            convertiti: Any = netCDF4.num2date(
                tempo[:], tempo.units, only_use_cftime_datetimes=False
            )
            istanti = np.atleast_1d(convertiti)
            giorni = [datetime(t.year, t.month, t.day).date() - timedelta(days=1) for t in istanti]
            tieni = np.array([inizio <= g <= fine for g in giorni])
            if not tieni.any():
                continue
            iy = np.array([int(np.abs(lats - lat).argmin()) for _, lat in celle])
            ix = np.array([int(np.abs(lons - lon).argmin()) for lon, _ in celle])
            # Fuori dal riquadro scaricato il più vicino è il bordo: non è la cella.
            dentro = (np.abs(lats[iy] - [c[1] for c in celle]) < _PASSO / 2) & (
                np.abs(lons[ix] - [c[0] for c in celle]) < _PASSO / 2
            )
            dati = np.ma.masked_invalid(ds.variables[_VARIABILE_NC][:])[tieni]
            per_nodo = dati[:, iy, ix]
            for k, nodo in enumerate(nodi):
                if not dentro[k]:
                    continue
                colonna = per_nodo[:, k]
                serie[nodo].extend(float(v) for v in colonna.compressed())
    return serie


def riferimenti(serie: dict[Nodo, list[float]], *, percentile: float) -> dict[Nodo, float | None]:
    """Il percentile di ogni serie; ``None`` sotto ``MIN_REFERENCE_DAYS``,
    con la stessa regola del riempimento da Open-Meteo."""
    return {
        n: percentile_of(v, percentile) if len(v) >= MIN_REFERENCE_DAYS else None
        for n, v in serie.items()
    }
