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

from glofas_ewds import (
    THRESHOLD_URL,
    flood_thresholds,
    read_threshold,
    threshold_file_name,
    threshold_url,
)

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry

log = get_logger(__name__)

URL = THRESHOLD_URL
#: I periodi di ritorno letti, in anni, e il nome del file per ciascuno.
PERIODI = (2, 5, 20)
FONTE = "glofas-v4-soglie"

Nodo = tuple[float, float]
Soglie = tuple[float | None, float | None, float | None]


def nome_file(anni: int) -> str:
    return threshold_file_name(anni)


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
        url = threshold_url(anni)

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


def leggi(path: Path, nodi: Sequence[Nodo]) -> list[float | None]:
    """La soglia di un file nella cella GloFAS di ogni nodo: ``glofas_ewds.read_threshold``."""
    return read_threshold(path, nodi)


def soglie(files: Sequence[Path], nodi: Sequence[Nodo]) -> dict[Nodo, Soglie]:
    """Per nodo, (piena da 2, da 5, da 20 anni) in m³/s, nell'ordine di :data:`PERIODI`.

    ``glofas_ewds.flood_thresholds``, rimesso nella terna che ``glofas_repo``
    salva: ``files`` sono quelli di :func:`scarica`, nell'ordine dei periodi.
    """
    per_nodo = flood_thresholds(dict(zip(PERIODI, files, strict=True)), nodi)
    return {n: (v.get(2), v.get(5), v.get(20)) for n, v in per_nodo.items()}


__all__ = ["FONTE", "PERIODI", "URL", "leggi", "nome_file", "scarica", "soglie"]
