"""Il catalogo delle piogge rare di un giorno, dall'archivio del radar (#643).

Le 24 ore di solo radar (SRT1) del giorno, più le 23 prima perché una finestra
di 24 ore che finisce all'una comincia il giorno prima; ``rare_events`` della
libreria trova dove la pioggia ha passato il livello dei dieci anni di quel
posto (i pixel dove il radar vede male restano fuori), e ``with_merging`` dice
se i pluviometri l'hanno vista. Si tengono gli eventi che finiscono nel giorno.

Senza archivio, o con un'ora mancante, si lavora su quello che c'è: un'ora
mancante rende ignote le finestre che la contengono, non asciutte.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from dpc_radar import Event, RainGrid, rare_events, with_merging

from limen.core.logging import get_logger
from limen.integrations.dpc.merging_archive import archivio_condiviso

log = get_logger(__name__)

_ORE_PRIMA = 23


def piogge_rare_del_giorno(cartella: Path, giorno: date) -> list[Event]:
    archivio = archivio_condiviso(cartella)
    inizio = datetime.combine(giorno, time(), UTC)
    letti = 0

    def fotogrammi() -> Iterator[RainGrid]:
        # Uno alla volta: 47 fotogrammi nazionali tenuti in una lista pesano
        # centinaia di MB nel processo del worker.
        nonlocal letti
        for h in range(-_ORE_PRIMA, 24):
            g = archivio.read("SRT1", inizio + timedelta(hours=h + 1))
            if g is not None:
                letti += 1
                yield g

    eventi = [
        with_merging(e, archivio)
        for e in rare_events(fotogrammi())
        if inizio < e.time <= inizio + timedelta(days=1)
    ]
    if not letti:
        log.info("dpc.piogge_rare.vuoto", giorno=giorno.isoformat())
        return []
    log.info(
        "dpc.piogge_rare.done",
        giorno=giorno.isoformat(),
        ore=letti,
        eventi=len(eventi),
        confermati=sum(e.confirmed is True for e in eventi),
    )
    return eventi
