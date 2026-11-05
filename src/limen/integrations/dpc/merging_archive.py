"""L'archivio locale del radar DPC: pioggia oraria corretta con i pluviometri.

L'API pubblica del DPC tiene circa cinque mesi di fotogrammi, poi li perde, e
il «Merging» (radar più pluviometri) non esiste in archivio pubblico: se non
lo salviamo noi, ogni mese ne sparisce uno.

Layout su disco, download idempotente e ricostruzione dell'ora (lo SRT1
riscalato perché le tre ore del blocco sommino al CUM3) vengono dal pacchetto
``dpc-radar`` (``dpc_radar.archive``), che legge anche gli ``assenti.txt``
scritti da Limen prima di lui. Qui restano tre cose di Limen: l'HTTP passa da
``_http`` (:func:`~limen.integrations.dpc.client.radar_archivio`), la cache
dei fotogrammi è **una per cartella** e protetta da un lock, perché le regioni
dello stesso sweep leggono gli stessi file da thread diversi, e un fotogramma
illeggibile logga ``integration.degraded``.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

from dpc_radar import RainGrid
from dpc_radar import archive as dpc_archive

from limen.core.logging import get_logger
from limen.integrations.dpc.client import radar_archivio
from limen.integrations.openmeteo.dtos import WeatherSample

log = get_logger(__name__)

percorso = dpc_archive.path
istanti = dpc_archive.times

#: Le 48 ore dello sweep toccano fino a 51 SRT1 e 17 CUM3, ~6,5 MB l'uno.
#: Con margine: a cache piena giusta, un fotogramma in più fa girare l'LRU
#: a vuoto su ogni regione (~530 MB).
_FOTOGRAMMI_IN_MEMORIA = 80


async def archivia(
    cartella: Path,
    *,
    giorni: int,
    massimo: int,
    adesso: datetime | None = None,
    recenti_prima: bool = False,
) -> dict[str, int]:
    """Scarica i fotogrammi che mancano, dal più vecchio: è quello che il DPC
    perderà per primo.

    Idempotente: un file già su disco non si riscarica, uno che il DPC non
    tiene più si annota e non si richiede. Si ferma a ``massimo`` richieste.
    ``recenti_prima`` è per lo sweep orario (#360): le ore appena cadute
    prima che il tetto se ne vada su fotogrammi vecchi bloccati.
    """
    adesso = adesso or datetime.now(UTC)
    report = await dpc_archive.archive(
        cartella,
        radar_archivio(),
        start=adesso - timedelta(days=giorni),
        # L'ultima ora non è ancora pubblicata con certezza.
        end=adesso - timedelta(hours=2),
        limit=massimo,
        newest_first=recenti_prima,
        now=adesso,
    )
    conti = {
        "scaricati": report.downloaded,
        "presenti": report.present,
        "persi": report.lost,
        "falliti": report.failed,
        "mb": report.bytes // 1_000_000,
    }
    log.info("dpc.archivio.done", cartella=str(cartella), giorni=giorni, **conti)
    return conti


class _ArchivioCondiviso(dpc_archive.MergingArchive):
    def __init__(self, cartella: Path) -> None:
        super().__init__(cartella, cache_frames=_FOTOGRAMMI_IN_MEMORIA)
        self._lock = threading.Lock()

    def read(self, product: str, time: datetime) -> RainGrid | None:
        # Sotto il lock anche la decodifica: due regioni che chiedono lo stesso
        # fotogramma lo decodificano una volta sola.
        file = percorso(self.folder, product, time)
        try:
            with self._lock:
                grid = super().read(product, time)
        except OSError as exc:
            # Permessi, o un file sparito fra stat e lettura: manca quel
            # fotogramma, non tutte le ore della regione.
            log.warning(
                "integration.degraded", source="dpc_merging_archive", file=str(file), error=str(exc)
            )
            return None
        if grid is None and file.exists():
            # Un file salvato da una risposta d'errore: il fotogramma manca, la
            # regione tiene le altre ore misurate.
            log.warning("integration.degraded", source="dpc_merging_archive", file=str(file))
        return grid


@cache
def _condiviso(cartella: Path) -> _ArchivioCondiviso:
    return _ArchivioCondiviso(cartella)


class MergingArchive:
    """Pioggia oraria corretta con i pluviometri, dall'archivio su disco."""

    def __init__(self, cartella: Path) -> None:
        self._archivio = _condiviso(cartella)

    def oraria(
        self, points: list[tuple[float, float]], start: datetime, end: datetime
    ) -> dict[datetime, list[float | None]]:
        """Pioggia di ogni ora ``(h-1, h]`` in ``(start, end]``, per punto (mm)."""
        return self._archivio.hourly(points, start, end)


def pioggia_dal_radar(
    grezzo: list[list[WeatherSample]], radar: dict[datetime, list[float | None]]
) -> list[list[WeatherSample]]:
    """La serie oraria di ogni nodo con la pioggia del radar dove c'è.

    Le ore che il radar non ha misurato tengono la pioggia del modello: un
    buco dell'archivio non è un'ora asciutta, e azzerarla abbasserebbe il
    punteggio proprio dove non si sa.
    """
    out: list[list[WeatherSample]] = []
    for k, serie in enumerate(grezzo):
        nuova = []
        for c in serie:
            ore = radar.get(c.timestamp)
            mm = ore[k] if ore is not None else None
            nuova.append(c if mm is None else c.model_copy(update={"precipitation_mm": mm}))
        out.append(nuova)
    return out
