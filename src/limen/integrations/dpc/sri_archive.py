"""L'archivio radar DPC 2010-2025 (IT-DPC-SRI) letto dal disco, per il backtest.

IT-DPC-SRI (Fondazione Bruno Kessler su dati DPC, CC BY-SA 4.0, Zenodo
10.5281/zenodo.18637608, arXiv 2602.15088) è il mosaico nazionale SRI —
intensità in mm/h, solo radar, senza pluviometri — in un unico Zarr v2: un
chunk per istante, 1400 x 1200 pixel da 1 km in Mercatore trasversa centrata
su 42°N 12,5°E, un fotogramma ogni 15 minuti fino al 2014, 10 fino al 2020,
5 dopo. Lo si legge senza zarr né xarray: basta il codec Blosc per
decomprimere un fotogramma.

È lo storico che l'API pubblica del DPC non dà (serve solo gli ultimi mesi):
il backtest ci rigioca le frane di ITALICA con la pioggia misurata al posto
di quella del modello, che il 10 ottobre 2026 a Melito vedeva 17 mm contro
176 (#235).

Un'ora coperta per meno di metà dai fotogrammi vale ``None``, «non
misurata»: un buco dell'archivio non è un'ora asciutta.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from pyproj import Transformer

from limen.core.logging import get_logger

log = get_logger(__name__)

_EPOCA = datetime(2010, 1, 1, tzinfo=UTC)
#: Il passo più lungo dell'archivio: un intervallo più largo è un buco, e il
#: fotogramma prima del buco non lo copre.
_PASSO_MAX_MIN = 15


class SriArchive:
    """Pioggia oraria in punti lon/lat, dallo Zarr IT-DPC-SRI su disco."""

    def __init__(self, path: Path) -> None:
        from numcodecs import Blosc

        self._path = path
        self._codec = Blosc()
        arr = json.loads((path / "RR" / ".zarray").read_text())
        self._shape = tuple(arr["shape"][1:])
        crs = json.loads((path / "crs" / ".zattrs").read_text())
        x0, dx, _, y0, _, dy = (float(v) for v in crs["GeoTransform"].split())
        self._x0, self._dx, self._y0, self._dy = x0, dx, y0, dy
        self._proj = Transformer.from_crs("EPSG:4326", crs["crs_wkt"], always_xy=True)
        self._minuti = np.frombuffer(self._decode(path / "time" / "0"), dtype="<i8")

    def _decode(self, file: Path) -> bytes:
        return bytes(self._codec.decode(file.read_bytes()))

    def pixel(self, points: list[tuple[float, float]]) -> list[tuple[int, int] | None]:
        """(riga, colonna) di ogni punto lon/lat; ``None`` fuori dalla griglia."""
        xs, ys = self._proj.transform([p[0] for p in points], [p[1] for p in points])
        out: list[tuple[int, int] | None] = []
        for x, y in zip(xs, ys, strict=True):
            r = int((y - self._y0) // self._dy)
            c = int((x - self._x0) // self._dx)
            dentro = 0 <= r < self._shape[0] and 0 <= c < self._shape[1]
            out.append((r, c) if dentro else None)
        return out

    def _fotogramma(self, i: int) -> np.ndarray | None:
        file = self._path / "RR" / f"{i}.0.0"
        if not file.exists():
            return None
        return np.frombuffer(self._decode(file), dtype="<f4").reshape(self._shape)

    def oraria(
        self, points: list[tuple[float, float]], start: datetime, end: datetime
    ) -> dict[datetime, list[float | None]]:
        """Pioggia di ogni ora ``(h-1, h]`` in ``(start, end]``, per punto (mm).

        Media delle intensità dei fotogrammi dell'ora, ciascuno pesato per il
        tratto che copre fino al successivo (al più 15 minuti); mediana 3x3
        attorno al pixel, come la produzione legge il «Merging».
        """
        pixel = self.pixel(points)
        a = int((start - _EPOCA).total_seconds() // 60)
        b = int((end - _EPOCA).total_seconds() // 60)
        lo = int(np.searchsorted(self._minuti, a, side="right"))
        hi = int(np.searchsorted(self._minuti, b, side="right"))
        somme: dict[int, np.ndarray] = {}
        coperti: dict[int, np.ndarray] = {}
        letti = mancanti = 0
        for i in range(lo, hi):
            m = int(self._minuti[i])
            dopo = int(self._minuti[i + 1]) if i + 1 < len(self._minuti) else m + 5
            peso = min(dopo - m, _PASSO_MAX_MIN)
            f = self._fotogramma(i)
            if f is None:
                mancanti += 1
                continue
            letti += 1
            valori = np.full(len(points), np.nan)
            for k, rc in enumerate(pixel):
                if rc is None:
                    continue
                r, c = rc
                finestra = f[max(0, r - 1) : r + 2, max(0, c - 1) : c + 2]
                validi = finestra[np.isfinite(finestra) & (finestra >= 0)]
                if validi.size:
                    valori[k] = float(np.median(validi))
            # Il fotogramma vale da `m` al successivo: sta nell'ora che si chiude dopo.
            ora = m // 60 + 1
            ok = np.isfinite(valori)
            somme.setdefault(ora, np.zeros(len(points)))[ok] += valori[ok] * peso
            coperti.setdefault(ora, np.zeros(len(points)))[ok] += peso
        if mancanti:
            log.warning("sri_archive.fotogrammi_mancanti", letti=letti, mancanti=mancanti)
        out: dict[datetime, list[float | None]] = {}
        for ora, somma in sorted(somme.items()):
            cop = coperti[ora]
            out[_EPOCA + timedelta(minutes=ora * 60)] = [
                float(s / c) if c >= 30 else None for s, c in zip(somma, cop, strict=True)
            ]
        return out
