"""Idempotent SQL migration runner.

Design goals:

* Pure-SQL migrations under :mod:`limen.data.migrations` — no Alembic, no
  Django, no ORM lock-in. The runner does not parse the SQL, it just
  executes each file and records the filename in ``schema_migrations``.
* Identical behaviour on local Docker PostgreSQL+PostGIS and on Neon
  (serverless). The optional ``pg_cron`` extension is created inside the SQL
  files inside a ``DO`` block that swallows errors, so missing-on-Neon is
  fine.
* Safe to run multiple times. Each file's checksum is recorded; running the
  same file again is a no-op, running it with different content is an error.
"""

from __future__ import annotations

import hashlib
import re
from importlib import resources
from typing import TYPE_CHECKING, Literal

import asyncpg

from limen.core.logging import get_logger
from limen.data.db import acquire

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pydantic import SecretStr

    from limen.config.settings import Settings

log = get_logger(__name__)

MIGRATIONS_PACKAGE = "limen.data.migrations"


_BOOTSTRAP_SQL = """\
CREATE TABLE IF NOT EXISTS schema_migrations (
    name        text PRIMARY KEY,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


def _discover_migrations() -> list[tuple[str, str]]:
    """Return a sorted list of ``(filename, sql_text)`` pairs."""
    files = sorted(
        f.name
        for f in resources.files(MIGRATIONS_PACKAGE).iterdir()
        if f.is_file() and f.name.endswith(".sql")
    )
    out: list[tuple[str, str]] = []
    for name in files:
        ref = resources.files(MIGRATIONS_PACKAGE).joinpath(name)
        out.append((name, ref.read_text(encoding="utf-8")))
    return out


# The pool's DB__COMMAND_TIMEOUT_SECONDS (30 s by default) is sized for
# operational queries. A migration that rebuilds a hot table copies millions
# of rows and rebuilds its indexes inside one statement, so it needs its own
# ceiling — without it the transaction is cancelled mid-rebuild and rolled
# back, which looks like a broken migration rather than a timeout.
_APPLY_TIMEOUT_SECONDS = 1800.0


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _already_applied(
    conn: asyncpg.Connection,
    name: str,
) -> str | None:
    row = await conn.fetchrow("SELECT checksum FROM schema_migrations WHERE name = $1", name)
    return None if row is None else str(row["checksum"])


async def run_migrations(only: Iterable[str] | None = None) -> list[str]:
    """Apply pending migrations.

    Args:
        only: Optional iterable of migration filenames to restrict the run to.

    Returns:
        The list of migration filenames that were applied during this call.
    """
    applied_now: list[str] = []
    whitelist = set(only) if only is not None else None

    async with acquire() as conn:
        await conn.execute(_BOOTSTRAP_SQL)

        for name, sql in _discover_migrations():
            if whitelist is not None and name not in whitelist:
                continue

            cs = _checksum(sql)
            previous = await _already_applied(conn, name)

            if previous is not None:
                if previous != cs:
                    raise RuntimeError(
                        f"Migration {name!r} has changed since it was applied "
                        f"(stored checksum={previous}, current={cs}). "
                        "Create a new migration file instead of editing applied ones."
                    )
                log.debug("migrate.skip", file=name)
                continue

            log.info("migrate.apply", file=name)
            async with conn.transaction():
                await conn.execute(sql, timeout=_APPLY_TIMEOUT_SECONDS)
                await conn.execute(
                    "INSERT INTO schema_migrations (name, checksum) VALUES ($1, $2)",
                    name,
                    cs,
                )
            applied_now.append(name)

    log.info("migrate.done", applied=len(applied_now), files=applied_now)
    return applied_now


# Finisce dentro un URL (pg_tileserv, il DSN dell'ingestore): un `@` o un `/`
# lo romperebbe, e l'unico segno sarebbe un servizio che non entra.
_PASSWORD_ESADECIMALE = re.compile(r"[0-9a-f]{32,}")

RuoloConPassword = Literal["limen_tiles", "limen_ingestore"]


async def imposta_password(
    ruolo: RuoloConPassword,
    password: SecretStr | None,
    *,
    variabile: str,
    obbligatoria: bool,
) -> None:
    """Dà a un ruolo ristretto (migrazioni 078, 079) la password del ``.env``.

    Il repo non la conosce, quindi non può stare nella migrazione. Senza
    password il servizio che usa il ruolo non entra (pg_tileserv) o resta sul
    pool principale (l'ingestore): lo si dice, ma non si rifiuta di servire
    l'API per questo.
    """
    if password is None or not password.get_secret_value():
        if obbligatoria:
            log.warning("migrate.ruolo_senza_password", ruolo=ruolo, variabile=variabile)
        return
    if not _PASSWORD_ESADECIMALE.fullmatch(password.get_secret_value()):
        log.warning("migrate.password_non_esadecimale", ruolo=ruolo, variabile=variabile)
        return
    try:
        async with acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT set_config('limen.ruolo', $1, true), "
                "set_config('limen.password', $2, true)",
                ruolo,
                password.get_secret_value(),
            )
            await conn.execute(
                "DO $$ BEGIN EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L', "
                "current_setting('limen.ruolo'), current_setting('limen.password')); END $$"
            )
    except asyncpg.PostgresError as exc:
        log.warning("migrate.password_fallita", ruolo=ruolo, error_type=type(exc).__name__)


async def crea_database_mlflow(settings: Settings) -> None:
    """Il database del registry MLflow, se manca e sta su questo server.

    ``initdb/01-mlflow-db.sql`` gira solo alla prima creazione del cluster: un
    volume già avviato o ripristinato restava senza, e il retrain lo scopriva
    dopo ore di arricchimento (#327). Le tabelle le crea MLflow al primo uso.
    """
    from limen.data.backup import mlflow_database

    nome = mlflow_database(settings.scoring.mlflow_tracking_uri, settings.db.connection_string)
    if nome is None:
        return
    try:
        async with acquire() as conn:
            if await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", nome):
                return
            quotato = await conn.fetchval("SELECT quote_ident($1)", nome)
            await conn.execute(f"CREATE DATABASE {quotato}")
    except asyncpg.PostgresError as exc:
        log.warning("migrate.mlflow_db_fallito", database=nome, error_type=type(exc).__name__)
        return
    log.info("migrate.mlflow_db_creato", database=nome)


async def imposta_password_dei_ruoli(settings: Settings) -> None:
    """Le password di tutti i ruoli ristretti, dall'API all'avvio e da ``limen migrate``."""
    await imposta_password(
        "limen_tiles",
        settings.db.tiles_password,
        variabile="DB__TILES_PASSWORD",
        obbligatoria=True,
    )
    await imposta_password(
        "limen_ingestore",
        settings.iot.cittadini.db_password,
        variabile="IOT__CITTADINI__DB_PASSWORD",
        obbligatoria=False,
    )
