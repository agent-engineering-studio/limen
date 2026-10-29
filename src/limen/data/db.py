"""Async PostgreSQL access (asyncpg) with a PostGIS geometry codec.

The codec converts ``GEOMETRY``/``GEOGRAPHY`` columns to/from
:class:`shapely.geometry.base.BaseGeometry` so that the rest of the codebase
can work with Shapely natively — without an ORM and without explicit
``ST_AsBinary``/``ST_GeomFromWKB`` calls in every query.

The pool itself is provider-agnostic: the *same* code talks to local Docker
PostgreSQL+PostGIS and to Neon (sslmode=require). Only
``DB__CONNECTION_STRING`` differs between environments.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from shapely import from_wkb, to_wkb
from shapely.geometry.base import BaseGeometry

from limen.config.settings import DBSettings, get_settings
from limen.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

log = get_logger(__name__)

# Default SRID for all geometry columns in the Limen schema.
SRID_WGS84 = 4326


def _encode_geometry(geom: BaseGeometry) -> str:
    """Encode a Shapely geometry as hex-encoded EWKB.

    asyncpg's ``format='text'`` codec expects a string; PostGIS accepts
    hex-encoded WKB on text input for geometry columns, which avoids round-
    tripping through ``ST_GeomFromWKB``. SRID is preserved via EWKB.
    """
    if not isinstance(geom, BaseGeometry):
        raise TypeError(
            f"PostGIS geometry codec expects a Shapely BaseGeometry, got {type(geom)!r}"
        )
    encoded = to_wkb(geom, hex=True, include_srid=True)
    return encoded if isinstance(encoded, str) else cast(bytes, encoded).decode("ascii")


def _decode_geometry(value: str) -> BaseGeometry:
    """Decode hex-encoded EWKB returned by PostGIS into a Shapely geometry."""
    return from_wkb(value)


async def _register_postgis(conn: asyncpg.Connection) -> None:
    """Register the PostGIS geometry codec on ``conn``.

    Uses text format with EWKB-hex which round-trips SRID information.
    """
    await conn.set_type_codec(
        "geometry",
        encoder=_encode_geometry,
        decoder=_decode_geometry,
        schema="public",
        format="text",
    )


async def register_postgis(conn: asyncpg.Connection) -> None:
    """Register the PostGIS geometry codec on a standalone connection.

    Public entry point for connections opened outside the global pool (e.g.
    the GeoServer-source loader talking to the mcp-geo-server PostGIS).
    """
    await _register_postgis(conn)


_pool: asyncpg.Pool | None = None
# Un pool diverso per il task corrente: l'ingestore dei sensori di terzi scrive
# con un ruolo ristretto (#267) passando dagli stessi repo di tutti gli altri.
# Una ContextVar e non un parametro: vale solo nel task che la imposta, e i
# repo non devono sapere chi li chiama.
_pool_del_task: ContextVar[asyncpg.Pool | None] = ContextVar("pool_del_task", default=None)


async def init_pool(settings: DBSettings | None = None) -> asyncpg.Pool:
    """Create the global asyncpg pool if not already created and return it.

    Idempotent: repeated calls return the same pool. The pool registers the
    PostGIS codec on each connection.
    """
    global _pool
    if _pool is not None:
        return _pool

    cfg = settings or get_settings().db
    log.info(
        "db.pool.init",
        dsn_host=_redact_dsn(cfg.connection_string),
        min_size=cfg.pool_min_size,
        max_size=cfg.pool_max_size,
    )
    _pool = await asyncpg.create_pool(
        dsn=cfg.connection_string,
        min_size=cfg.pool_min_size,
        max_size=cfg.pool_max_size,
        statement_cache_size=cfg.statement_cache_size,
        command_timeout=cfg.command_timeout_seconds,
        init=_register_postgis,
    )
    return _pool


async def close_pool() -> None:
    """Close the global pool if it exists."""
    global _pool
    if _pool is not None:
        log.info("db.pool.close")
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the current pool. Raises if :func:`init_pool` has not been called."""
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first")
    return _pool


@asynccontextmanager
async def lifespan_pool(
    settings: DBSettings | None = None,
) -> AsyncIterator[asyncpg.Pool]:
    """Open the pool, yield it, close it only if *we* opened it.

    Ownership-aware: if a caller (typically the FastAPI lifespan or a
    test fixture) has already initialised the global pool, this helper
    treats the pool as borrowed and leaves it open on exit. Standalone
    CLI runners that nest this context get the open/close pair they
    expect.
    """
    owned = _pool is None
    pool = await init_pool(settings)
    try:
        yield pool
    finally:
        if owned:
            await close_pool()


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection from the global pool as an async context manager.

    Inside :func:`usa_pool`, from that pool instead.
    """
    pool = _pool_del_task.get() or get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def connessione_dedicata() -> AsyncIterator[asyncpg.Connection]:
    """Una connessione fuori dal pool, per chi la tiene a lungo (un lock di
    sessione): presa dal pool, con un pool da una connessione bloccherebbe
    ogni ``acquire`` del lavoro che protegge."""
    cfg = get_settings().db
    conn = await asyncpg.connect(
        dsn=cfg.connection_string, statement_cache_size=cfg.statement_cache_size
    )
    try:
        yield conn
    finally:
        await conn.close()


@contextmanager
def usa_pool(pool: asyncpg.Pool) -> Iterator[None]:
    """Fa passare da ``pool`` ogni :func:`acquire` del task corrente."""
    token = _pool_del_task.set(pool)
    try:
        yield
    finally:
        _pool_del_task.reset(token)


def dsn_con_ruolo(dsn: str, ruolo: str, password: str) -> str:
    """Lo stesso database, con un altro utente: il ruolo ristretto di un servizio.

    Si sostituiscono solo utente e password: la lista degli host resta com'è,
    anche con più host (``db1:5432,db2:5432``), che ``urlsplit`` non sa leggere.
    """
    parti = urlsplit(dsn)
    host = parti.netloc.rpartition("@")[2]
    return urlunsplit(parti._replace(netloc=f"{ruolo}:{password}@{host}"))


async def crea_pool(dsn: str, *, max_size: int) -> asyncpg.Pool:
    """Un pool a parte, col codec PostGIS come quello globale."""
    cfg = get_settings().db
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=max_size,
        statement_cache_size=cfg.statement_cache_size,
        command_timeout=cfg.command_timeout_seconds,
        init=_register_postgis,
    )


def _redact_dsn(dsn: str) -> str:
    """Return ``dsn`` with the password component replaced by ``***``."""
    try:
        scheme, rest = dsn.split("://", 1)
        if "@" in rest:
            cred, host = rest.split("@", 1)
            if ":" in cred:
                user, _ = cred.split(":", 1)
                return f"{scheme}://{user}:***@{host}"
        return dsn
    except ValueError:
        return dsn
