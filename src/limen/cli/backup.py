"""``limen backup`` e ``limen restore`` — lo stato fuori dal server (#304).

    limen backup                  un backup adesso, come il passo notturno
    limen backup elenco           i backup completi sullo store
    limen restore --conferma      ripristina l'ultimo backup completo
    limen restore --chiave backup/2026-10-24T02-05-00Z/ --conferma

Il ripristino sovrascrive il database di ``DB__CONNECTION_STRING`` (o di
``BACKUP__DSN``): per questo chiede ``--conferma``, e si rifiuta se altri client
sono connessi o se il database è a una migrazione diversa da quella del backup
(``--forza`` per farlo comunque). Un ripristino che non ritrova le righe del
manifest esce con 1. Dall'host di oggi, dove ``pg_dump`` sta solo nel container del
database, ``BACKUP__COMANDO_PG="docker exec -i limen-postgres"`` e
``BACKUP__DSN`` con l'indirizzo visto da dentro quel container.
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from limen.api.jobs._tracking import tracked
from limen.api.jobs.ids import JOB_NIGHTLY
from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.data.backup import (
    BackupError,
    backup_completi,
    esegui_backup,
    mlflow_database,
    ripristina,
)
from limen.data.db import acquire, lifespan_pool
from limen.data.object_store import ObjectStore, build_backup_store
from limen.data.repos import map_views_repo, partitions_repo

log = get_logger(__name__)


def _dsn(settings: Settings) -> str:
    cfg = settings.backup
    return cfg.dsn.get_secret_value() if cfg.dsn else settings.db.connection_string


def _store(settings: Settings) -> ObjectStore | None:
    store = build_backup_store(settings.backup)
    if store is None:
        log.error("backup.non_configurato", hint="BACKUP__BUCKET (o BACKUP__ROOT in prova)")
    return store


async def _fai(settings: Settings) -> int:
    store = _store(settings)
    if store is None:
        return 1
    with tempfile.TemporaryDirectory(prefix="limen-backup-") as d:
        async with lifespan_pool():
            # La stessa riga del passo notturno: un backup a mano azzera
            # l'allarme `backup.stale` come uno di notte.
            async with tracked(JOB_NIGHTLY, scope="backup") as metrics, acquire() as conn:
                esito = await esegui_backup(
                    cfg=settings.backup,
                    dsn=_dsn(settings),
                    conn=conn,
                    store=store,
                    adesso=datetime.now(UTC),
                    lavoro=Path(d),
                    mlflow=mlflow_database(settings.scoring.mlflow_tracking_uri),
                )
                metrics.update(chiave=esito.chiave, byte=esito.byte, a_mano=True)
                if esito.avvisi:
                    metrics.update(avvisi=list(esito.avvisi), status="warn")
    log.info("backup.cli", chiave=esito.chiave, byte=esito.byte, cancellati=len(esito.cancellati))
    return 0


async def _elenco(settings: Settings) -> int:
    store = _store(settings)
    if store is None:
        return 1
    completi = await backup_completi(store)
    for chiave in completi:
        log.info("backup.disponibile", chiave=chiave)
    log.info("backup.elenco", completi=len(completi))
    return 0


async def _ripristina(
    settings: Settings, *, chiave: str | None, conferma: bool, forza: bool
) -> int:
    if not conferma:
        log.error(
            "restore.senza_conferma",
            hint="sovrascrive il database: rilancia con --conferma, con API e worker fermi",
        )
        return 1
    store = _store(settings)
    if store is None:
        return 1
    with tempfile.TemporaryDirectory(prefix="limen-restore-") as d:
        # Una connessione sola e non il pool: le connessioni in più del pool
        # sarebbero «altri client», e il ripristino si rifiuterebbe sempre.
        conn = await asyncpg.connect(settings.db.connection_string)
        try:
            fatto = await ripristina(
                cfg=settings.backup,
                dsn=_dsn(settings),
                conn=conn,
                store=store,
                lavoro=Path(d),
                chiave=chiave,
                forza=forza,
            )
        finally:
            await conn.close()
    async with lifespan_pool():
        # Le partizioni dei prossimi giorni, prima che uno sweep ci scriva;
        # poi la vista della mappa, che il dump porta vuota.
        create = await partitions_repo.ensure()
        righe = await map_views_repo.refresh_latest_risk()
    log.info("restore.fatto", chiave=fatto, partizioni=create, latest_risk=righe)
    return 0


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    b = top.add_parser("backup", help="backup dello stato sullo store BACKUP__* (#304)")
    b.add_argument("azione", nargs="?", choices=("fai", "elenco"), default="fai")
    r = top.add_parser("restore", help="ripristina un backup (#304): sovrascrive il database")
    r.add_argument("--chiave", help="backup/<istante>/ (default: l'ultimo completo)")
    r.add_argument("--conferma", action="store_true", help="sì, sovrascrivi il database")
    r.add_argument(
        "--forza",
        action="store_true",
        help="anche con altri client connessi o a una migrazione diversa",
    )


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        if args.command == "restore":
            return await _ripristina(
                settings, chiave=args.chiave, conferma=args.conferma, forza=args.forza
            )
        if args.azione == "elenco":
            return await _elenco(settings)
        return await _fai(settings)
    except BackupError as exc:
        log.error("backup.errore", error=str(exc))
        return 1


__all__ = ["build_subparser", "run"]
