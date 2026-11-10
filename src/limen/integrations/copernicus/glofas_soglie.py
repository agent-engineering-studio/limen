"""Le soglie GloFAS v4 dei periodi di ritorno, per nodo (#522).

Tre NetCDF globali a 0,05° (~165 MB l'uno), pubblici e senza credenziali,
sulla wiki ECMWF («GloFAS auxiliary data»): la portata della piena da 2, 5 e
20 anni di ogni cella. Per ogni nodo del ramo fluviale si legge la cella che
il nodo legge già per la previsione e il riferimento — quella che Open-Meteo
serve, un passo a est della dichiarata (`glofas_ewds.cells`): sbagliare cella
su un fiume vale un fattore dieci.

Il download passa dal client condiviso in streaming, dentro
``call_with_retry``: tenere 165 MB in memoria con ``fetch_with_retry`` no.
Un file già sul disco non si riscarica.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from glofas_ewds.cells import cell_indices, open_meteo_cell

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry

log = get_logger(__name__)

URL = (
    "https://confluence.ecmwf.int/download/attachments/242067380/flood_threshold_glofas_v4_rl_{}.nc"
)
#: I periodi di ritorno letti, in anni, e il nome del file per ciascuno.
PERIODI = (2, 5, 20)
FONTE = "glofas-v4-soglie"

Nodo = tuple[float, float]
Soglie = tuple[float | None, float | None, float | None]


def nome_file(anni: int) -> str:
    return f"flood_threshold_glofas_v4_rl_{float(anni):.1f}.nc"


async def scarica(cartella: Path) -> list[Path]:
    """I tre file in ``cartella``; uno già scaricato non si richiede."""
    cartella.mkdir(parents=True, exist_ok=True)
    client = await SharedHttpClient.get()
    out: list[Path] = []
    for anni in PERIODI:
        path = cartella / nome_file(anni)
        out.append(path)
        if path.exists():
            continue
        parziale = path.with_name(f"{path.name}.part")
        url = URL.format(f"{float(anni):.1f}")

        async def _giu(url: str = url, parziale: Path = parziale) -> None:
            async with client.stream("GET", url, follow_redirects=True, timeout=600) as resp:
                resp.raise_for_status()
                with parziale.open("wb") as f:
                    async for blocco in resp.aiter_bytes(1 << 20):
                        f.write(blocco)

        await call_with_retry(_giu)
        parziale.rename(path)
        log.info("glofas_soglie.scaricato", file=path.name, mb=path.stat().st_size >> 20)
    return out


def _variabile(ds: Any) -> tuple[Any, Any, Any]:
    variabili = ds.variables
    nomi = [k for k, v in variabili.items() if v.ndim == 2]
    if len(nomi) != 1:
        raise ValueError(f"attesa una variabile 2-D, trovate {nomi}")
    lat = next(v for k, v in variabili.items() if k.lower().startswith("lat"))
    lon = next(v for k, v in variabili.items() if k.lower().startswith("lon"))
    return variabili[nomi[0]], lat, lon


def leggi(path: Path, nodi: Sequence[Nodo]) -> list[float | None]:
    """La soglia di un file nella cella GloFAS di ogni nodo; ``None`` se mascherata o fuori.

    Si legge solo il rettangolo che contiene i nodi: il file è il mondo.
    """
    if not nodi:
        return []
    import netCDF4

    with netCDF4.Dataset(path) as ds:
        var, lat, lon = _variabile(ds)
        lats = np.asarray(lat[:], dtype=float)
        lons = np.asarray(lon[:], dtype=float)
        celle = [open_meteo_cell(x, y) for x, y in nodi]
        righe, colonne, dentro = cell_indices(lats, lons, celle)
        r0, r1 = int(righe.min()), int(righe.max()) + 1
        c0, c1 = int(colonne.min()), int(colonne.max()) + 1
        blocco = np.ma.filled(np.ma.asarray(var[r0:r1, c0:c1], dtype=float), np.nan)
    out: list[float | None] = []
    for r, c, ok in zip(righe, colonne, dentro, strict=True):
        v = float(blocco[r - r0, c - c0]) if ok else float("nan")
        out.append(v if np.isfinite(v) and v > 0 else None)
    return out


def soglie(files: Sequence[Path], nodi: Sequence[Nodo]) -> dict[Nodo, Soglie]:
    """Per nodo, (piena da 2, da 5, da 20 anni) in m³/s, nell'ordine di :data:`PERIODI`."""
    colonne = [leggi(f, nodi) for f in files]
    return {n: (colonne[0][i], colonne[1][i], colonne[2][i]) for i, n in enumerate(nodi)}


__all__ = ["FONTE", "PERIODI", "URL", "leggi", "nome_file", "scarica", "soglie"]
