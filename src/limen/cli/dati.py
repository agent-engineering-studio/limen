"""``limen dati`` — la coda dei download dei dati statici (#402).

``stato`` dice a che punto è ogni voce del catalogo; ``scarica`` mette in
coda le voci chieste e il **worker** le esegue, una alla volta. Il comando non
scarica niente da sé: un download da 22 GB lanciato da un terminale muore
con il terminale, uno del worker riprende dopo un riavvio.
"""

from __future__ import annotations

import argparse

from limen.config.catalogo_dati import CatalogoDati, Livello, carica_catalogo
from limen.core.installazione import byte_stimati, scaricabili
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import dati_download_repo as repo

log = get_logger(__name__)


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = top.add_parser("dati", help="download dei dati statici, eseguiti dal worker (#402)")
    sub = p.add_subparsers(dest="dati_command", required=True)
    sub.add_parser("stato", help="a che punto è ogni voce del catalogo")
    s = sub.add_parser("scarica", help="mette in coda le voci; le scarica il worker")
    gruppo = s.add_mutually_exclusive_group(required=True)
    gruppo.add_argument("voci", nargs="*", default=[], metavar="VOCE")
    gruppo.add_argument("--essenziali", action="store_true", help="le voci essenziali")
    gruppo.add_argument("--tutte", action="store_true", help="tutte le voci che si scaricano")


def scelte(args: argparse.Namespace, catalogo: CatalogoDati) -> list[str]:
    """Le voci da accodare. Solleva ``SystemExit`` su un id sconosciuto o derivato."""
    da_scaricare = [v for v in catalogo.voci if v.deriva_da is None]
    if args.tutte:
        return [v.id for v in da_scaricare]
    if args.essenziali:
        return [v.id for v in da_scaricare if v.livello is Livello.ESSENZIALE]
    try:
        return scaricabili(catalogo, args.voci)
    except ValueError as exc:
        raise SystemExit(f"{exc} Vedi `limen dati stato`.") from exc


def _peso(byte: float | None) -> str:
    if byte is None:
        return "—"
    return f"{byte / 1e6:.0f} MB" if byte < 1e9 else f"{byte / 1e9:.1f} GB"


async def stato(catalogo: CatalogoDati) -> int:
    righe = {r.voce: r for r in await repo.elenco()}
    print(f"\n  {'voce':22s} {'livello':12s} {'stato':11s} {'scaricati':>19s}  errore")
    for v in catalogo.voci:
        r = righe.get(v.id)
        if v.deriva_da is not None:
            stato_, gb, errore = "derivato", "", ""
        elif r is None:
            stato_, gb, errore = "mai chiesto", f"circa {_peso(v.peso_gb * 1e9)}", ""
        else:
            stato_, gb = r.stato, f"{_peso(r.byte_fatti)} / {_peso(r.byte_totali)}"
            errore = r.errore or ""
        print(f"  {v.id:22s} {v.livello.value:12s} {stato_:11s} {gb:>19s}  {errore}")
    print()
    return 0


async def run(args: argparse.Namespace) -> int:
    catalogo = carica_catalogo()
    async with lifespan_pool():
        await run_migrations()
        if args.dati_command == "stato":
            return await stato(catalogo)
        voci = scelte(args, catalogo)
        accodate = await repo.accoda(voci, byte_totali=byte_stimati(catalogo))
        gia = sorted(set(voci) - set(accodate))
        print(
            f"In coda: {', '.join(accodate) or 'nessuna'}"
            + (f". Già in corso: {', '.join(gia)}" if gia else "")
            + ".\nLe scarica il worker; `limen dati stato` dice a che punto sono."
        )
    return 0


__all__ = ["build_subparser", "run", "scelte"]
