"""``limen static-snapshot`` — i fattori per cella senza i raster (#305).

    limen static-snapshot export           uno snapshot sullo store BACKUP__*
    limen static-snapshot elenco           gli snapshot completi
    limen static-snapshot import           carica l'ultimo (dopo migrate e seed)
    limen static-snapshot import --chiave statico/2026-10-26T14-00-00Z/ --forza

    limen static-snapshot pacchetto --uscita DIR      il pacchetto rapido in tre licenze (#406)
    limen static-snapshot import --da-url URL         scarica manifest e file, poi importa
    limen static-snapshot import --da-cartella DIR    importa un pacchetto già scaricato

Lo store è quello del backup (``BACKUP__*``), sotto ``statico/``, e i comandi
PostgreSQL passano da ``BACKUP__COMANDO_PG`` come per il backup. L'import si
rifiuta su una migrazione o una griglia diverse da quelle dello snapshot, e
non sostituisce fattori già calcolati senza ``--forza``.

Il pacchetto non passa dallo store: si scrive in una cartella, da caricare a
mano come asset di una release, e si importa da un URL o da una cartella.
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from limen.cli.backup import _dsn, _store
from limen.config.catalogo_dati import carica_catalogo
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.backup import BackupError
from limen.data.db import acquire, lifespan_pool
from limen.data.pacchetto_statico import esporta_pacchetto, importa_pacchetto, scarica_pacchetto
from limen.data.static_snapshot import esporta, importa, snapshot_completi
from limen.integrations._http import SharedHttpClient

log = get_logger(__name__)


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    s = top.add_parser(
        "static-snapshot", help="snapshot dei fattori per cella, senza i raster (#305)"
    )
    s.add_argument("azione", choices=("export", "import", "elenco", "pacchetto"))
    s.add_argument("--chiave", help="statico/<istante>/ (default: l'ultimo completo)")
    s.add_argument("--forza", action="store_true", help="sostituisci i fattori già calcolati qui")
    s.add_argument("--uscita", type=Path, help="pacchetto: la cartella in cui scriverlo")
    s.add_argument("--da-url", help="import del pacchetto: l'URL del suo manifest.json")
    s.add_argument("--da-cartella", type=Path, help="import di un pacchetto già scaricato")


async def _pacchetto(args: argparse.Namespace) -> int:
    try:
        async with lifespan_pool(), acquire() as conn:
            if args.azione == "pacchetto":
                if args.uscita is None:
                    log.error("static_snapshot.pacchetto", error="serve --uscita DIR")
                    return 1
                await esporta_pacchetto(
                    conn=conn,
                    catalogo=carica_catalogo(),
                    uscita=args.uscita,
                    adesso=datetime.now(UTC),
                )
                return 0
            with tempfile.TemporaryDirectory(prefix="limen-pacchetto-") as d:
                cartella = args.da_cartella or Path(d)
                if args.da_url:
                    try:
                        await scarica_pacchetto(args.da_url, cartella)
                    finally:
                        await SharedHttpClient.aclose()
                await importa_pacchetto(conn=conn, cartella=cartella, forza=args.forza)
        return 0
    except BackupError as exc:
        log.error("static_snapshot.errore", error=str(exc))
        return 1


async def run(args: argparse.Namespace) -> int:
    if args.azione == "pacchetto" or (
        args.azione == "import" and (args.da_url or args.da_cartella)
    ):
        return await _pacchetto(args)
    settings = get_settings()
    store = _store(settings)
    if store is None:
        return 1
    try:
        if args.azione == "elenco":
            completi = await snapshot_completi(store)
            for chiave in completi:
                log.info("static_snapshot.disponibile", chiave=chiave)
            log.info("static_snapshot.elenco", completi=len(completi))
            return 0
        with tempfile.TemporaryDirectory(prefix="limen-statico-") as d:
            async with lifespan_pool(), acquire() as conn:
                if args.azione == "export":
                    fatto = await esporta(
                        cfg=settings.backup,
                        dsn=_dsn(settings),
                        conn=conn,
                        store=store,
                        adesso=datetime.now(UTC),
                        lavoro=Path(d),
                    )
                else:
                    fatto = await importa(
                        cfg=settings.backup,
                        dsn=_dsn(settings),
                        conn=conn,
                        store=store,
                        lavoro=Path(d),
                        chiave=args.chiave,
                        forza=args.forza,
                    )
        log.info("static_snapshot.cli", azione=args.azione, chiave=fatto.chiave, byte=fatto.byte)
        return 0
    except BackupError as exc:
        log.error("static_snapshot.errore", error=str(exc))
        return 1


__all__ = ["build_subparser", "run"]
