"""La coda dei download dei dati statici (migrazione 086, #402).

Chi chiede un download (la CLI oggi, la pagina di installazione con #404)
mette la voce in coda e notifica il canale ``dati_download``; il worker è
l'unico che esegue. Il worker gira a una replica, ma la presa usa comunque
``FOR UPDATE SKIP LOCKED``: costa niente e due consumatori per errore non
scaricherebbero due volte lo stesso file da 22 GB.

Le scritture sollevano: una richiesta persa sarebbe un download che chi
installa crede partito.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from limen.data.db import acquire

#: Gli stati del CHECK della migrazione 086.
Stato = Literal["in_coda", "in_corso", "fatto", "errore"]

#: La riga che non è un download: caricare nelle celle quello che si è scaricato
#: (#405). Sta nella stessa coda per averne gli stessi stati, la ripresa dopo un
#: riavvio e il tetto ai tentativi. Non è una voce del catalogo.
ELABORAZIONE = "elaborazione"
#: Il canale di NOTIFY che sveglia il worker.
CANALE = "dati_download"
#: Oltre queste prese interrotte da un riavvio, la voce si chiude in errore.
TENTATIVI_MASSIMI = 3
#: Chiave del lock consultivo che tiene fuori dagli stessi file il worker e
#: `make static-data` dall'host: due download dello stesso `.part` in append
#: mescolano i byte, e il DTM butterebbe 22 GB al controllo dell'md5.
_LOCK_DOWNLOAD = 0x4C494D454E_0402  # "LIMEN" #402


@dataclass(frozen=True, slots=True)
class StatoDownload:
    voce: str
    stato: Stato
    byte_fatti: int
    byte_totali: int | None
    richiesto_il: datetime
    avviato_il: datetime | None
    aggiornato_il: datetime
    finito_il: datetime | None
    errore: str | None
    tentativi: int


async def accoda(voci: Sequence[str], *, byte_totali: dict[str, int]) -> list[str]:
    """Mette in coda le voci e sveglia il worker; restituisce quelle accodate.

    Una voce già in corso non si tocca: rimetterla in coda la farebbe
    ripartire alla fine di quella che sta scaricando.
    """
    async with acquire() as conn, conn.transaction():
        accodate: list[str] = []
        for voce in voci:
            riga = await conn.fetchval(
                """
                INSERT INTO dati_download (voce, stato, byte_totali)
                VALUES ($1, 'in_coda', $2)
                ON CONFLICT (voce) DO UPDATE
                   SET stato = 'in_coda', byte_totali = EXCLUDED.byte_totali,
                       richiesto_il = now(), aggiornato_il = now(),
                       avviato_il = NULL, finito_il = NULL, errore = NULL, tentativi = 0
                 WHERE dati_download.stato <> 'in_corso'
                RETURNING voce
                """,
                voce,
                byte_totali.get(voce),
            )
            if riga is not None:
                accodate.append(str(riga))
        if accodate:
            await conn.execute("SELECT pg_notify($1, '')", CANALE)
    return accodate


async def prendi_prossima() -> str | None:
    """La voce in coda da più tempo, portata ``in_corso``; ``None`` se la coda è vuota."""
    async with acquire() as conn:
        voce = await conn.fetchval(
            """
            UPDATE dati_download
               SET stato = 'in_corso', avviato_il = now(), aggiornato_il = now(),
                   tentativi = tentativi + 1
             WHERE voce = (
                   SELECT voce FROM dati_download
                    WHERE stato = 'in_coda'
                    ORDER BY richiesto_il
                    LIMIT 1
                      FOR UPDATE SKIP LOCKED)
            RETURNING voce
            """
        )
    return None if voce is None else str(voce)


async def avanza(voce: str, byte_fatti: int) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE dati_download SET byte_fatti = $2, aggiornato_il = now() "
            "WHERE voce = $1 AND stato = 'in_corso'",
            voce,
            byte_fatti,
        )


async def chiudi(voce: str, *, errore: str | None, byte_fatti: int | None = None) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE dati_download
               SET stato = CASE WHEN $2::text IS NULL THEN 'fatto' ELSE 'errore' END,
                   errore = $2, byte_fatti = coalesce($3, byte_fatti),
                   finito_il = now(), aggiornato_il = now()
             WHERE voce = $1
            """,
            voce,
            errore,
            byte_fatti,
        )


async def riaccoda_interrotte() -> list[str]:
    """Le voci rimaste ``in_corso`` da un worker che si è fermato, di nuovo in coda.

    Va chiamata solo all'avvio del worker, prima di prendere qualsiasi voce:
    a una replica, in quel momento nessuno sta scaricando davvero. La ripresa
    del file è compito del download (il DTM riparte dal suo ``.part``). Una
    voce interrotta ``TENTATIVI_MASSIMI`` volte si chiude in errore: è lei, con
    ogni probabilità, a far cadere il worker.
    """
    async with acquire() as conn, conn.transaction():
        await conn.execute(
            """
            UPDATE dati_download
               SET stato = 'errore', finito_il = now(), aggiornato_il = now(),
                   errore = CASE WHEN voce = $2 THEN 'Il caricamento' ELSE 'Il download' END
                            || ' si è interrotto ' || tentativi
                            || ' volte facendo ripartire il worker: '
                            || 'guarda i log del worker prima di riprovare.'
             WHERE stato = 'in_corso' AND tentativi >= $1
            """,
            TENTATIVI_MASSIMI,
            ELABORAZIONE,
        )
        righe = await conn.fetch(
            "UPDATE dati_download SET stato = 'in_coda', aggiornato_il = now() "
            "WHERE stato = 'in_corso' RETURNING voce"
        )
    return [str(r["voce"]) for r in righe]


@asynccontextmanager
async def blocco_download() -> AsyncIterator[bool]:
    """``True`` se nessun altro sta scaricando: il lock resta finché si è dentro.

    Lo prendono il worker per ogni voce e ``limen geodati-sync`` /
    ``limen fetch-static`` per tutto il loro giro. Chi lo trova occupato non
    aspetta: rinuncia e lo dice.
    """
    async with acquire() as conn:
        preso = bool(await conn.fetchval("SELECT pg_try_advisory_lock($1)", _LOCK_DOWNLOAD))
        try:
            yield preso
        finally:
            if preso:
                await conn.execute("SELECT pg_advisory_unlock($1)", _LOCK_DOWNLOAD)


async def elenco() -> list[StatoDownload]:
    async with acquire() as conn:
        righe = await conn.fetch(
            "SELECT voce, stato, byte_fatti, byte_totali, richiesto_il, avviato_il, "
            "aggiornato_il, finito_il, errore, tentativi FROM dati_download ORDER BY richiesto_il"
        )
    return [StatoDownload(**dict(r)) for r in righe]


__all__ = [
    "CANALE",
    "ELABORAZIONE",
    "TENTATIVI_MASSIMI",
    "Stato",
    "StatoDownload",
    "accoda",
    "avanza",
    "blocco_download",
    "chiudi",
    "elenco",
    "prendi_prossima",
    "riaccoda_interrotte",
]
