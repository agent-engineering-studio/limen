"""L'archivio locale del radar DPC: pioggia oraria corretta con i pluviometri.

L'API pubblica del DPC tiene circa cinque mesi di fotogrammi, poi li perde.
Lo storico IT-DPC-SRI (2010-2025) è solo radar, e sottostima: in Puglia, nel
settembre 2016, leggeva fra il 10 e l'80 % dei pluviometri. Il «Merging» è la
correzione con i pluviometri, ma non esiste in archivio pubblico: se non lo
salviamo noi, ogni mese ne sparisce uno.

Due prodotti, perché il «Merging» più breve dura tre ore:

* ``CUM3`` alle 00, 03, ..., 21 UTC: blocchi da tre ore che non si
  sovrappongono, radar più pluviometri, 0,01° in EPSG:4326;
* ``SRT1`` a ogni ora piena: la cumulata oraria del solo radar, 1 km.

La pioggia di un'ora è SRT1 riscalata perché le tre ore del blocco sommino
esattamente al CUM3: il «Merging» dice quanta, il radar dice quando. Se il
radar non ha visto niente e i pluviometri sì, il blocco si divide in parti
uguali; senza CUM3 resta SRT1; senza nessuno dei due l'ora è «non misurata».

Layout: ``<cartella>/<PRODOTTO>/<AAAA>/<MM>/<GG>/<PRODOTTO>_<AAAAMMGGhhmm>.tif``,
più ``assenti.txt`` per prodotto con i fotogrammi che il DPC non tiene più.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio

from limen.core.logging import get_logger
from limen.integrations.dpc.client import ASSENTE, SriGrid, scarica_fotogramma

log = get_logger(__name__)

#: Prodotto → passo in ore fra due fotogrammi archiviati.
PRODOTTI = {"CUM3": 3, "SRT1": 1}
#: Sotto questa somma oraria il radar «non ha visto niente» nel blocco (mm).
_RADAR_SECCO_MM = 0.1


def percorso(cartella: Path, prodotto: str, t: datetime) -> Path:
    return cartella / prodotto / f"{t:%Y/%m/%d}" / f"{prodotto}_{t:%Y%m%d%H%M}.tif"


def istanti(prodotto: str, dal: datetime, al: datetime) -> list[datetime]:
    """Gli istanti archiviati di ``prodotto`` in ``[dal, al]``, dal più vecchio."""
    passo = PRODOTTI[prodotto]
    t = dal.replace(minute=0, second=0, microsecond=0)
    if t < dal:
        t += timedelta(hours=1)
    t += timedelta(hours=(-t.hour) % passo)
    out = []
    while t <= al:
        out.append(t)
        t += timedelta(hours=passo)
    return out


def _assenti(cartella: Path, prodotto: str) -> Path:
    return cartella / prodotto / "assenti.txt"


async def archivia(
    cartella: Path, *, giorni: int, massimo: int, adesso: datetime | None = None
) -> dict[str, int]:
    """Scarica i fotogrammi che mancano, dal più vecchio: è quello che il DPC
    perderà per primo.

    Idempotente: un file già su disco non si riscarica, uno che il DPC non
    tiene più si annota e non si richiede. Si ferma a ``massimo`` download.
    """
    adesso = adesso or datetime.now(UTC)
    # L'ultima ora non è ancora pubblicata con certezza.
    al = adesso - timedelta(hours=2)
    dal = adesso - timedelta(days=giorni)
    conti = {"scaricati": 0, "presenti": 0, "persi": 0, "falliti": 0}
    byte = 0
    for prodotto in PRODOTTI:
        assenti_f = _assenti(cartella, prodotto)
        noti = set(assenti_f.read_text().split()) if assenti_f.exists() else set()
        for t in istanti(prodotto, dal, al):
            if conti["scaricati"] + conti["persi"] + conti["falliti"] >= massimo:
                break
            dest = percorso(cartella, prodotto, t)
            chiave = f"{t:%Y%m%d%H%M}"
            if dest.exists() or chiave in noti:
                conti["presenti"] += 1
                continue
            dati = await scarica_fotogramma(prodotto, t)
            if dati == ASSENTE:
                assenti_f.parent.mkdir(parents=True, exist_ok=True)
                with assenti_f.open("a") as f:
                    f.write(chiave + "\n")
                conti["persi"] += 1
            elif isinstance(dati, bytes):
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".tmp")
                tmp.write_bytes(dati)
                tmp.rename(dest)
                conti["scaricati"] += 1
                byte += len(dati)
            else:
                conti["falliti"] += 1
    conti["mb"] = byte // 1_000_000
    log.info("dpc.archivio.done", cartella=str(cartella), giorni=giorni, **conti)
    return conti


def _leggi(file: Path, t: datetime) -> SriGrid | None:
    if not file.exists():
        return None
    with rasterio.open(file) as ds:
        dati = ds.read(1).astype(np.float32)
        dati[~np.isfinite(dati)] = -9999.0
        return SriGrid(data=dati, transform=ds.transform, crs=ds.crs, observed_at=t)


class MergingArchive:
    """Pioggia oraria corretta con i pluviometri, dall'archivio su disco."""

    def __init__(self, cartella: Path) -> None:
        self._cartella = cartella

    def _campiona(
        self, prodotto: str, t: datetime, points: list[tuple[float, float]]
    ) -> list[float | None]:
        grid = _leggi(percorso(self._cartella, prodotto, t), t)
        return grid.sample(points) if grid is not None else [None] * len(points)

    def oraria(
        self, points: list[tuple[float, float]], start: datetime, end: datetime
    ) -> dict[datetime, list[float | None]]:
        """Pioggia di ogni ora ``(h-1, h]`` in ``(start, end]``, per punto (mm)."""
        out: dict[datetime, list[float | None]] = {}
        primo = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        for fine in istanti("CUM3", primo, end + timedelta(hours=2)):
            ore = [fine - timedelta(hours=k) for k in (2, 1, 0)]
            merging = self._campiona("CUM3", fine, points)
            radar = [self._campiona("SRT1", h, points) for h in ore]
            for j, h in enumerate(ore):
                if not (start < h <= end):
                    continue
                valori: list[float | None] = []
                for k in range(len(points)):
                    blocco = [r[k] for r in radar]
                    valori.append(_disaggrega(merging[k], blocco, j))
                out[h] = valori
        return out


def _disaggrega(merging: float | None, radar: list[float | None], j: int) -> float | None:
    """La quota dell'ora ``j`` del blocco nel totale «Merging»."""
    if merging is None:
        return radar[j]
    misurate = [r for r in radar if r is not None]
    somma = sum(max(r, 0.0) for r in misurate)
    if somma < _RADAR_SECCO_MM or len(misurate) < len(radar):
        return merging / len(radar)
    r = radar[j]
    return merging * max(r, 0.0) / somma if r is not None else None
