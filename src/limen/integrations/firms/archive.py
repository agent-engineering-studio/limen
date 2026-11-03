"""Archivio storico FIRMS per paese — hotspot dal 2000 (#66).

**Nessun login Earthdata, nessuna consegna via email.** La issue prevedeva il
percorso del portale di download (che chiede un'utenza e spedisce lo zip per
posta), ma FIRMS pubblica anche gli archivi *per paese e per anno* come CSV
statici in chiaro:

    https://firms.modaps.eosdis.nasa.gov/data/country/{sorgente}/{anno}/{sorgente}_{anno}_{paese}.csv

Verificato: `modis_2020_Italy.csv` risponde 200 con 360 KB di CSV,
`viirs-snpp_2020_Italy.csv` con 1,7 MB. L'archivio italiano completo pesa
**35 MB**. È la terza volta in questo progetto che una fonte creduta chiusa è
aperta, dopo EFFIS e il layer CLMS dell'EEA: prima di accettare una barriera
di accreditamento, conviene provare l'URL.

Copertura reale, misurata sondando gli anni (ultima verifica 2026-11-03):

* ``modis`` — dal **2000** al 2025;
* ``viirs-snpp`` — dal **2012** al 2025;
* ``viirs-noaa20`` / ``viirs-noaa21`` — **non pubblicati** come archivio per
  paese, nonostante siano nel feed NRT.

L'anno in corso non c'è ancora: quel tratto lo copre il feed NRT
(`limen firms-sync`), e le due cose non si sovrappongono. URL, prodotti e
riconoscimento del CSV, download e cache vengono dal pacchetto
``firms-client``.

Le righe finiscono nella stessa `fire_hotspots` dell'NRT, con `source`
distinta (``MODIS_SP`` / ``VIIRS_SNPP_SP``, dove SP è la *standard
processing* di FIRMS). Distinta e non uguale: sono prodotti diversi con
qualità diversa, e schiacciarli sullo stesso valore renderebbe impossibile
sapere da dove viene una detection. La chiave naturale contiene `source`,
quindi l'upsert resta idempotente e i due prodotti convivono.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import firms_client as firms
import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.data.repos.fire_repo import FireHotspot
from limen.integrations._http import SharedHttpClient
from limen.integrations.firms.client import ConfidenceLevel, parse_hotspot_csv

log = get_logger(__name__)

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


@dataclass(frozen=True, slots=True)
class ArchiveProduct:
    """Un prodotto d'archivio: come si chiama nell'URL e come in banca dati."""

    product: firms.ArchiveProduct
    #: Valore di `fire_hotspots.source`. `_SP` = standard processing, per
    #: distinguerlo dalle righe `_NRT` dello stesso strumento.
    source: str

    @property
    def slug(self) -> str:
        return self.product.slug

    @property
    def first_year(self) -> int:
        return self.product.first_year


#: I due prodotti effettivamente pubblicati per paese. NOAA-20 e NOAA-21
#: restano fuori perché l'archivio per paese non li espone — non è una scelta.
ARCHIVE_PRODUCTS: tuple[ArchiveProduct, ...] = (
    ArchiveProduct(product=firms.MODIS, source="MODIS_SP"),
    ArchiveProduct(product=firms.VIIRS_SNPP, source="VIIRS_SNPP_SP"),
)

DEFAULT_COUNTRY = "Italy"


def _cache_dir() -> Path:
    """Cartella di cache. Layout theme-first: `data/fires/firms/`."""
    return Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser() / "fires" / "firms"


async def fetch_archive_year(
    *,
    product: ArchiveProduct,
    year: int,
    country: str = DEFAULT_COUNTRY,
    min_confidence: ConfidenceLevel = "nominal",
    min_confidence_pct: int = 50,
    min_frp_mw: float = 0.0,
    use_cache: bool = True,
) -> list[FireHotspot]:
    """Gli hotspot di un anno, dalla cache o dalla rete.

    Download e cache sono di ``firms-client`` (``download_archive``): un file
    nella cartella è intero, perché si scarica in un ``.part`` rinominato a
    fine download, e un anno non pubblicato non lascia niente su disco.
    ``use_cache=False`` cancella il file e lo riscarica.

    Degrada come il resto delle integrazioni: un anno non disponibile dà lista
    vuota e una riga di log, e gli altri anni continuano.
    """
    directory = _cache_dir()
    cached = directory / firms.archive_filename(product.product, year, country)
    if not use_cache:
        cached.unlink(missing_ok=True)
    hit = cached.is_file()
    try:
        path = await firms.download_archive(
            await SharedHttpClient.get(), product.product, year, country, directory
        )
    except firms.FirmsError as exc:
        log.info("firms.archive.unavailable", product=product.slug, year=year, error=str(exc))
        return []
    except _DEGRADATION_EXC as exc:
        log.warning(
            "integration.degraded",
            label="firms.archive",
            product=product.slug,
            year=year,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return []
    if path is None:
        log.info("firms.archive.unavailable", product=product.slug, year=year, status=404)
        return []
    log.info(
        "firms.archive.cache_hit" if hit else "firms.archive.downloaded",
        product=product.slug,
        year=year,
        bytes=path.stat().st_size,
        path=str(path),
    )

    hotspots = parse_hotspot_csv(
        path.read_text(encoding="utf-8", errors="replace"),
        source=product.source,
        min_confidence=min_confidence,
        min_confidence_pct=min_confidence_pct,
        min_frp_mw=min_frp_mw,
    )
    log.info("firms.archive.parsed", product=product.slug, year=year, hotspots=len(hotspots))
    return hotspots


def archive_years(product: ArchiveProduct, *, until_year: int) -> list[int]:
    """Gli anni da provare per un prodotto, dal suo primo pubblicato."""
    return firms.archive_years(product.product, until=until_year)


__all__ = [
    "ARCHIVE_PRODUCTS",
    "DEFAULT_COUNTRY",
    "ArchiveProduct",
    "archive_years",
    "fetch_archive_year",
]
