"""La maschera delle sorgenti fisse FIRMS, imparata dagli archivi per paese.

L'API NRT non ha la colonna ``type``: senza maschera l'ILVA di Taranto, le
raffinerie e l'Etna arrivano come un incendio qualunque. ``firms-client``
impara cella per cella (0,01°) cosa gli archivi hanno visto lì
(``build_static_mask``, funzione pura); qui restano il download, che passa da
`fetch_with_retry` e riusa la cache CSV di ``limen ingest-fire-history``, e il
salvataggio. Misurata dal pacchetto sull'Italia 2025 con ``type`` nascosto:
99,3 % delle sorgenti fisse riconosciute, 3 % di righe di vegetazione
mascherate.

La maschera si salva una volta per anno d'archivio: l'anno nuovo, quando
FIRMS lo pubblica, la ricostruisce. Degrada a ``None`` (righe NRT senza
``type``, come prima) e non solleva mai.
"""

from __future__ import annotations

import os
from datetime import date
from itertools import chain
from pathlib import Path

import firms_client as firms

from limen.core.logging import get_logger
from limen.integrations.firms.archive import (
    ARCHIVE_PRODUCTS,
    DEFAULT_COUNTRY,
    ArchiveProduct,
    archive_text,
    archive_years,
)

log = get_logger(__name__)

#: VIIRS S-NPP e non MODIS: 375 m contro 1 km, la stessa risoluzione dei
#: feed NRT che la maschera etichetta.
_PRODUCT: ArchiveProduct = next(p for p in ARCHIVE_PRODUCTS if p.product == firms.VIIRS_SNPP)


def _mask_path(*, country: str, first: int, last: int) -> Path:
    root = Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser()
    name = f"static-mask_{_PRODUCT.slug}_{country}_{first}-{last}.json"
    return root / "fires" / "firms" / name


async def load_static_mask(
    *, country: str = DEFAULT_COUNTRY, today: date | None = None
) -> firms.StaticMask | None:
    """La maschera di ``country`` fino all'anno scorso: dal file, o costruita ora."""
    last = (today or date.today()).year - 1
    first = _PRODUCT.first_year
    path = _mask_path(country=country, first=first, last=last)
    if path.is_file():
        try:
            return firms.StaticMask.load(path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("firms.static_mask.unreadable", path=str(path), error=str(exc))

    years = archive_years(_PRODUCT, until_year=last)
    texts = {
        year: text
        for year in years
        if (text := await archive_text(product=_PRODUCT, year=year, country=country)) is not None
    }
    if not texts:
        log.warning("integration.degraded", label="firms.static_mask", country=country)
        return None
    mask = firms.build_static_mask(
        chain.from_iterable(firms.parse_csv(text) for text in texts.values()),
        meta={"country": country, "product": _PRODUCT.slug, "years": sorted(texts)},
    )
    # Un anno caduto per un errore di rete farebbe una maschera monca per un
    # anno intero: si salva solo se manca al più l'ultimo, che FIRMS può non
    # aver ancora pubblicato.
    if set(years) - set(texts) <= {last}:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            mask.save(path)
        except OSError as exc:
            log.warning("firms.static_mask.not_saved", path=str(path), error=str(exc))
    log.info(
        "firms.static_mask.built",
        country=country,
        years=len(texts),
        static_cells=len(mask.cells),
        saved=path.is_file(),
    )
    return mask


__all__ = ["load_static_mask"]
