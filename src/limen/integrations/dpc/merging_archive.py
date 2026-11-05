"""L'archivio locale del radar DPC: pioggia oraria corretta con i pluviometri.

L'API pubblica del DPC tiene circa cinque mesi di fotogrammi, poi li perde, e
il «Merging» (radar più pluviometri) non esiste in archivio pubblico: se non
lo salviamo noi, ogni mese ne sparisce uno.

Layout su disco, download idempotente e ricostruzione dell'ora (lo SRT1
riscalato perché le tre ore del blocco sommino al CUM3) vengono dal pacchetto
``dpc-radar`` (``dpc_radar.archive``), che legge anche gli ``assenti.txt``
scritti da Limen prima di lui. Qui restano tre cose di Limen: l'HTTP passa da
``_http`` (:func:`~limen.integrations.dpc.client.radar_archivio`), la cache
dei fotogrammi è **una per cartella**, perché le regioni dello stesso sweep
leggono gli stessi file, e quello che il pacchetto scrive sul suo logger
diventa ``integration.degraded``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

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


class _DegradoArchivio(logging.Handler):
    """Un fotogramma che manca o non si legge, come ogni altro degrado di Limen.

    Il pacchetto toglie dal messaggio il link firmato di S3.
    """

    def emit(self, record: logging.LogRecord) -> None:
        log.warning("integration.degraded", source="dpc_merging_archive", error=record.getMessage())


_logger_archivio = logging.getLogger(dpc_archive.__name__)
_logger_archivio.addHandler(_DegradoArchivio())
_logger_archivio.propagate = False


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


@cache
def _condiviso(cartella: Path) -> dpc_archive.MergingArchive:
    return dpc_archive.MergingArchive(cartella, cache_frames=_FOTOGRAMMI_IN_MEMORIA)


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
