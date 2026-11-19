"""``limen resoconto-radar SLUG`` — il radar di un evento verificato, in quattro file (#643).

Per un evento di ``verifiche_eventi`` scrive il resoconto di ``dpc_radar.report``
sul suo giorno (UTC; due giorni, in due cartelle, per un evento a meno di sei
ore dalla mezzanotte) e su un riquadro intorno al punto: ``facts.json`` (ogni
numero con il fotogramma da cui viene), ``report.md`` (un testo che cita solo
quei numeri, controllato prima di salvarlo), ``map.png`` (solo radar accanto
al «Merging») e ``hourly.png`` (la pioggia ora per ora nel punto più piovoso).
È il materiale per l'articolo delle Verifiche: la skill ``limen-fact-check``
lo cita, non lo ricalcola.

I fotogrammi vengono dall'archivio del «Merging» se c'è
(``RADAR_ARCHIVE__CARTELLA``), altrimenti dall'API del DPC (33 richieste,
solo per gli ultimi cinque mesi). Il bollettino è quello emesso la vigilia.
Report in ``LIMEN_REPORTS_DIR/resoconti-radar/<slug>/``.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from dpc_radar import DpcRadarError
from dpc_radar.report import build, download

from limen.cli.misura_radar import bollettino_per
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.dpc import bollettini
from limen.integrations.dpc.client import radar_archivio
from limen.integrations.dpc.merging_archive import archivio_condiviso

log = get_logger(__name__)

#: Il riquadro intorno al punto, gradi: un comune non basta a vedere il temporale.
_MEZZO_LATO_LON = 0.3
_MEZZO_LATO_LAT = 0.2
#: Un evento con l'ora nota più vicino di così alla mezzanotte UTC ha due giorni.
_VICINO_ALLA_MEZZANOTTE = timedelta(hours=6)


async def run(slug: str) -> int:
    async with lifespan_pool(), acquire() as conn:
        row = await conn.fetchrow(
            "SELECT evento_at, precisione_ora, ST_X(geom) AS lon, ST_Y(geom) AS lat "
            "FROM verifiche_eventi WHERE slug = $1 AND geom IS NOT NULL",
            slug,
        )
    if row is None:
        log.error("resoconto_radar.evento_sconosciuto", slug=slug)
        return 1
    lon, lat = float(row["lon"]), float(row["lat"])
    bbox = (
        lon - _MEZZO_LATO_LON,
        lat - _MEZZO_LATO_LAT,
        lon + _MEZZO_LATO_LON,
        lat + _MEZZO_LATO_LAT,
    )
    cfg = get_settings().radar_archive
    resoconti = []
    try:
        nomi = await bollettini.nomi()
        for giorno in giorni_dell_evento(row["evento_at"], row["precisione_ora"]):
            read = (
                archivio_condiviso(Path(cfg.cartella)).read
                if cfg.attivo
                else await download(radar_archivio(), giorno)
            )
            nome = bollettino_per(nomi, giorno)
            letto = await bollettini.scarica(nome) if nome is not None else None
            resoconti.append(
                (giorno, build(read, bbox, giorno, bulletins=[letto] if letto is not None else []))
            )
    finally:
        await SharedHttpClient.aclose()
    base = Path(os.getenv("LIMEN_REPORTS_DIR", "reports")) / "resoconti-radar" / slug
    scritti: list[Path] = []
    for giorno, resoconto in resoconti:
        cartella = base if len(resoconti) == 1 else base / giorno.isoformat()
        try:
            scritti += resoconto.save(cartella)
        except ImportError:  # matplotlib è nel gruppo `report`: senza, solo fatti e testo
            scritti += resoconto.save(cartella, images=False)
        except DpcRadarError as exc:
            log.error("resoconto_radar.testo_rifiutato", slug=slug, error=str(exc))
            return 1
    log.info("resoconto_radar.done", slug=slug, file=[str(p) for p in scritti])
    return 0


def giorni_dell_evento(quando: datetime, precisione: str) -> list[date]:
    """Il giorno UTC dell'evento e, se l'ora è nota e sta a meno di
    ``_VICINO_ALLA_MEZZANOTTE`` dalla mezzanotte, anche quello accanto: un
    resoconto copre un giorno, e la pioggia di un evento all'una di notte è
    caduta il giorno prima."""
    t = quando.astimezone(UTC)
    giorno = t.date()
    if precisione == "T3":
        return [giorno]
    inizio = datetime.combine(giorno, time(), UTC)
    if t - inizio < _VICINO_ALLA_MEZZANOTTE:
        return [giorno - timedelta(days=1), giorno]
    if inizio + timedelta(days=1) - t < _VICINO_ALLA_MEZZANOTTE:
        return [giorno, giorno + timedelta(days=1)]
    return [giorno]
