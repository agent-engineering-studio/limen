"""Backup e ripristino su un database vuoto, con PostgreSQL vero (#304).

`pg_dump` 16 sta nel container di prova, non sull'host: i comandi passano da
``docker exec -i <container>``, come dall'host di produzione con
``BACKUP__COMANDO_PG``. Senza la CLI di Docker (o con un database esterno) il
test si salta.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import pytest

from limen.config.settings import BackupSettings, ObjectStoreBackend
from limen.data.backup import BackupError, backup_completi, esegui_backup, ripristina
from limen.data.db import acquire
from limen.data.object_store.filesystem import FilesystemObjectStore

pytestmark = pytest.mark.integration

ADESSO = datetime(2026, 10, 24, 2, 5, tzinfo=UTC)
# Come la vede `pg_dump` da dentro il container; la password passa da
# PGPASSWORD (`docker exec -e`), non dagli argomenti.
INTERNO = "postgresql://limen:limen@localhost:5432"


def _container(dsn: str) -> str:
    if shutil.which("docker") is None:
        pytest.skip("serve la CLI di Docker per pg_dump nel container")
    porta = urlsplit(dsn).port
    cid = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"publish={porta}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not cid:
        pytest.skip("nessun container pubblica la porta del database di prova")
    return cid.splitlines()[0]


@pytest.fixture
async def destinazione(
    reset_db: None, postgres_container: str
) -> AsyncIterator[asyncpg.Connection]:
    """Un database vuoto accanto a quello di prova, e una connessione sola."""
    async with acquire() as conn:
        await conn.execute("DROP DATABASE IF EXISTS limen_ripristino WITH (FORCE)")
        await conn.execute("CREATE DATABASE limen_ripristino")
    url = urlsplit(postgres_container)
    dest = await asyncpg.connect(url._replace(path="/limen_ripristino").geturl())
    try:
        yield dest
    finally:
        await dest.close()
        async with acquire() as conn:
            await conn.execute("DROP DATABASE IF EXISTS limen_ripristino WITH (FORCE)")


async def _backup(
    cid: str, tmp_path: Path, *, cartelle: str = ""
) -> tuple[BackupSettings, FilesystemObjectStore]:
    impostazioni = BackupSettings(
        backend=ObjectStoreBackend.FILESYSTEM,
        root=tmp_path / "store",
        comando_pg=f"docker exec -i {cid}",
        cartelle=cartelle,
    )
    store = FilesystemObjectStore(tmp_path / "store")
    async with acquire() as conn:
        await esegui_backup(
            cfg=impostazioni,
            dsn=f"{INTERNO}/limen",
            conn=conn,
            store=store,
            adesso=ADESSO,
            lavoro=tmp_path / "lavoro",
        )
    return impostazioni, store


async def _ripristina(
    cfg: BackupSettings,
    store: FilesystemObjectStore,
    dest: asyncpg.Connection,
    tmp_path: Path,
    **kw: bool,
) -> str:
    return await ripristina(
        cfg=cfg,
        dsn=f"{INTERNO}/limen_ripristino",
        conn=dest,
        store=store,
        lavoro=tmp_path / "ripristino",
        **kw,
    )


async def test_backup_e_ripristino_su_un_database_vuoto(
    destinazione: asyncpg.Connection, postgres_container: str, tmp_path: Path
) -> None:
    cid = _container(postgres_container)
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO landslide_events (id, source, event_time, geom) "
            "VALUES ('frana-1', 'IR', '2016-10-30', ST_SetSRID(ST_MakePoint(13.1, 42.8), 4326))"
        )
        # `app_cache` è nell'elenco «solo schema»: deve tornare vuota.
        await conn.execute(
            "INSERT INTO app_cache (key, value, expires_at) VALUES ('k', '{}', now())"
        )
        # La versione di uno strato solo schema: dopo il ripristino si dimentica,
        # quella di una tabella salvata resta.
        await conn.execute(
            "INSERT INTO dataset_versions (source, dataset, version) VALUES "
            "('osm', 'roads', 'h1'), ('ispra', 'iffi', 'h2')"
        )
        migrazioni = await conn.fetchval("SELECT count(*) FROM schema_migrations")

    mlruns = tmp_path / "mlruns"
    (mlruns / "0").mkdir(parents=True)
    (mlruns / "0" / "meta.yaml").write_text("name: limen-landslide\n")
    cfg, store = await _backup(cid, tmp_path, cartelle=str(mlruns))
    [chiave] = await backup_completi(store)
    assert chiave == "backup/2026-10-24T02-05-00Z/"
    manifest = json.loads(await store.get(chiave + "manifest.json"))
    assert set(manifest["file"]) == {"limen.dump", "ruoli.sql", "mlruns.tar.gz"}
    assert manifest["righe"]["public.landslide_events"] == 1
    assert "public.app_cache" not in manifest["righe"]

    shutil.rmtree(mlruns)
    assert await _ripristina(cfg, store, destinazione, tmp_path) == chiave
    # Idempotente: il secondo giro, sulla migrazione giusta, sostituisce.
    assert await _ripristina(cfg, store, destinazione, tmp_path) == chiave
    assert (mlruns / "0" / "meta.yaml").read_text() == "name: limen-landslide\n"

    dest = destinazione
    # Una sola: il secondo ripristino sostituisce, non aggiunge.
    assert await dest.fetch("SELECT id FROM landslide_events") == [("frana-1",)]
    assert await dest.fetchval("SELECT count(*) FROM app_cache") == 0
    assert await dest.fetchval("SELECT count(*) FROM schema_migrations") == migrazioni
    assert await dest.fetch("SELECT source FROM dataset_versions ORDER BY 1") == [("ispra",)]
    # I GRANT ai ruoli ristretti tornano con le tabelle (078, 079).
    assert await dest.fetchval(
        "SELECT has_table_privilege('limen_ingestore', 'sensor_observations', 'INSERT')"
    )
    assert await dest.fetchval("SELECT ensure_partitions('risk_assessments', 2)") >= 0


async def test_un_ripristino_che_non_ritrova_le_righe_fallisce(
    destinazione: asyncpg.Connection, postgres_container: str, tmp_path: Path
) -> None:
    """«Writes do raise»: le righe promesse dal manifest devono esserci."""
    cid = _container(postgres_container)
    cfg, store = await _backup(cid, tmp_path)
    [chiave] = await backup_completi(store)
    manifest = json.loads(await store.get(chiave + "manifest.json"))
    manifest["righe"]["public.landslide_events"] += 5
    await store.put(chiave + "manifest.json", json.dumps(manifest).encode())
    with pytest.raises(BackupError, match="righe diverse"):
        await _ripristina(cfg, store, destinazione, tmp_path)


async def test_un_database_a_un_altra_migrazione_si_rifiuta(
    destinazione: asyncpg.Connection, postgres_container: str, tmp_path: Path
) -> None:
    cid = _container(postgres_container)
    cfg, store = await _backup(cid, tmp_path)
    await destinazione.execute(
        "CREATE TABLE schema_migrations (name text PRIMARY KEY, checksum text, "
        "applied_at timestamptz)"
    )
    await destinazione.execute(
        "INSERT INTO schema_migrations VALUES ('999_futuro.sql', 'x', now())"
    )
    with pytest.raises(BackupError, match="migrazione 999_futuro"):
        await _ripristina(cfg, store, destinazione, tmp_path)


async def test_un_altro_client_connesso_ferma_il_ripristino(
    destinazione: asyncpg.Connection, postgres_container: str, tmp_path: Path
) -> None:
    cid = _container(postgres_container)
    cfg, store = await _backup(cid, tmp_path)
    url = urlsplit(postgres_container)
    altro = await asyncpg.connect(url._replace(path="/limen_ripristino").geturl())
    try:
        with pytest.raises(BackupError, match="client connessi"):
            await _ripristina(cfg, store, destinazione, tmp_path)
    finally:
        await altro.close()
