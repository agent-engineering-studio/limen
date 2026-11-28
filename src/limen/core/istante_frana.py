"""L'istante di una frana datata: una regola sola, quella di tutte le librerie.

Una frana con l'ora vale a quell'ora. Una frana con il solo giorno vale alla
**fine del suo giorno, ora di Roma**: la mezzanotte locale dopo quel giorno
(il giorno di calendario più uno, nel fuso, non «+24 ore»: le due cose
differiscono nei giorni del cambio d'ora). È l'ultimo momento in cui la frana
può essere caduta, quindi la pioggia prima di lui è tutta quella che può
averla innescata. La regola è ``ispra_idrogeo.dated.instant_utc`` (0.15).

Prima ogni misura aveva la sua: mezzogiorno di Roma all'importazione
(FraneItalia, ``limen importa-eventi``), ``+24 h`` in ``pioggia_frane``,
``+23 h`` in ``misura-innesco``, la mezzanotte UTC più 24 ore in
``misura-soglia-radar``.

Le righe di ``landslide_events`` restano come sono: per una data senza ora
l'``event_time`` salvato è un momento qualunque di quel giorno locale
(mezzogiorno, la mezzanotte, le 20 di una data convenzionale), e da lì si
legge solo il giorno. Riscriverle è una migrazione a parte.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ispra_idrogeo.dated import ROME, instant_utc


def istante_frana(quando: datetime, con_ora: bool) -> datetime:
    """L'istante in UTC di una frana salvata a ``quando``.

    ``con_ora``: la data dice l'ora, che ``quando`` porta già. Altrimenti conta
    solo il giorno di ``quando`` a Roma, e l'istante è la fine di quel giorno.
    """
    if con_ora:
        return quando.astimezone(UTC)
    giorno = quando.astimezone(ROME).date().isoformat()
    return instant_utc({"start": giorno, "end": giorno, "time": None})


__all__ = ["istante_frana"]
