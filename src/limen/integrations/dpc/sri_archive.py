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

La lettura è quella di ``dpc_radar.history.SriHistory`` (#643): la stessa che
Limen aveva scritto per conto suo, più il riconoscimento dei fotogrammi
corrotti (752 su 1.039.785: il disco intero di un radar pieno di pioggia
violenta, o chiazze piatte sopra i 100 mm/h, quasi tutti nel 2011 e nel 2014),
che si leggono come mancanti. Qui si contano e si scrivono nel log di ogni
backtest, e si segnala una finestra che comincia prima del 2018: fino al 2017
il mosaico leggeva circa due terzi di oggi, e un backtest che attraversa il
2018 confronta due strumenti diversi. La mappa del bias di dpc-radar non si
applica allo storico: è costruita sui mesi del 2026, e lo strumento di prima
del 2018 non è quello.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from dpc_radar.history import SriHistory, suspect

from limen.core.logging import get_logger

log = get_logger(__name__)

#: Da qui in poi il mosaico è lo strumento di oggi (climatologia di dpc-radar).
STRUMENTO_DI_OGGI = datetime(2018, 1, 1, tzinfo=UTC)


class SriArchive(SriHistory):
    """Pioggia oraria in punti lon/lat, dallo Zarr IT-DPC-SRI su disco."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._letti = 0
        self._sospetti = 0

    def frame(self, i: int) -> np.ndarray | None:
        f = super().frame(i)
        if f is not None:
            self._letti += 1
            self._sospetti += bool(suspect(f))
        return f

    def oraria(
        self, points: list[tuple[float, float]], start: datetime, end: datetime
    ) -> dict[datetime, list[float | None]]:
        """Pioggia di ogni ora ``(h-1, h]`` in ``(start, end]``, per punto (mm)."""
        self._letti = self._sospetti = 0
        out = self.hourly(points, start, end)
        log.info(
            "sri_archive.letti",
            dal=start.isoformat(),
            al=end.isoformat(),
            fotogrammi=self._letti,
            corrotti=self._sospetti,
        )
        if start < STRUMENTO_DI_OGGI:
            log.warning(
                "sri_archive.prima_del_2018",
                dal=start.isoformat(),
                note="fino al 2017 il mosaico leggeva circa due terzi di oggi",
            )
        return out
