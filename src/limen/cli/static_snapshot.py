"""``limen static-snapshot`` — i fattori per cella senza i raster (#305).

    limen static-snapshot export           uno snapshot sullo store BACKUP__*
    limen static-snapshot elenco           gli snapshot completi
    limen static-snapshot import           carica l'ultimo (dopo migrate e seed)
    limen static-snapshot import --chiave statico/2026-10-26T14-00-00Z/ --forza

Lo store è quello del backup (``BACKUP__*``), sotto ``statico/``, e i comandi
PostgreSQL passano da ``BACKUP__COMANDO_PG`` come per il backup. L'import si
rifiuta su una migrazione o una griglia diverse da quelle dello snapshot, e
non sostituisce fattori già calcolati senza ``--forza``.
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from limen.cli.backup import _dsn, _store
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.backup import BackupError
from limen.data.db import acquire, lifespan_pool
from limen.data.static_snapshot import esporta, importa, snapshot_completi

log = get_logger(__name__)


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    s = top.add_parser(
        "static-snapshot", help="snapshot dei fattori per cella, senza i raster (#305)"
    )
    s.add_argument("azione", choices=("export", "import", "elenco"))
    s.add_argument("--chiave", help="statico/<istante>/ (default: l'ultimo completo)")
    s.add_argument("--forza", action="store_true", help="sostituisci i fattori già calcolati qui")


async def run(args: argparse.Namespace) -> int:
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
