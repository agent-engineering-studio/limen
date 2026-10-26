"""Snapshot statico: fattori per cella e mosaico idraulico senza i raster (#305).

Come il test del backup, ``pg_dump`` sta nel container di prova e i comandi
passano da ``docker exec -i``; senza la CLI di Docker il test si salta.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from limen.cli.seed import run as run_seed
from limen.config.settings import BackupSettings, ObjectStoreBackend
from limen.data.backup import BackupError
from limen.data.db import acquire
from limen.data.object_store.filesystem import FilesystemObjectStore
from limen.data.static_snapshot import esporta, importa
from tests.conftest import SEED_SMALL_AOI
from tests.integration.test_backup_ripristino import INTERNO, _container

pytestmark = pytest.mark.integration

ADESSO = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)


@pytest.fixture
async def strato(reset_db: None) -> AsyncIterator[None]:
    """Un'AOI seminata con qualche fattore, un poligono idraulico e un'impronta."""
    await run_seed(only=[SEED_SMALL_AOI])
    async with acquire() as conn:
        await conn.execute("TRUNCATE flood_hazard_subdiv, fire_events")
        await conn.execute(
            """
            INSERT INTO fire_events (cell_id, event_date, hotspots, sources)
            SELECT id, DATE '2024-08-10', 3, ARRAY['VIIRS'] FROM grid_cells ORDER BY id LIMIT 2
            """
        )
        await conn.execute(
            """
            INSERT INTO cell_static_factors (cell_id, slope_deg, landuse_code, s_static)
            SELECT id, 12.5, '311', 0.4 FROM grid_cells ORDER BY id LIMIT 50
            """
        )
        await conn.execute(
            """
            INSERT INTO flood_hazard_subdiv (id, hazard_class, hazard_class_norm, geom)
            VALUES ('P3-1', 'P3', 1.0,
                    ST_GeomFromText('POLYGON((7.3 45.7,7.4 45.7,7.4 45.8,7.3 45.7))', 4326))
            """
        )
        await conn.execute(
            "INSERT INTO dataset_versions (source, dataset, version, metadata) "
            "VALUES ('static_bootstrap', 'dem:it-valle-d-aosta', 'v-dem', '{\"grid_cells\": 1}')"
        )
    yield
    async with acquire() as conn:
        await conn.execute("TRUNCATE flood_hazard_subdiv, fire_events")


def _cfg(cid: str, tmp_path: Path) -> tuple[BackupSettings, FilesystemObjectStore]:
    cfg = BackupSettings(
        backend=ObjectStoreBackend.FILESYSTEM,
        root=tmp_path / "store",
        comando_pg=f"docker exec -i {cid}",
    )
    return cfg, FilesystemObjectStore(tmp_path / "store")


async def _esporta(cfg: BackupSettings, store: FilesystemObjectStore, tmp_path: Path) -> str:
    async with acquire() as conn:
        fatto = await esporta(
            cfg=cfg,
            dsn=f"{INTERNO}/limen",
            conn=conn,
            store=store,
            adesso=ADESSO,
            lavoro=tmp_path / "export",
        )
    return fatto.chiave


async def _importa(
    cfg: BackupSettings, store: FilesystemObjectStore, tmp_path: Path, **kw: bool
) -> None:
    async with acquire() as conn:
        await importa(
            cfg=cfg,
            dsn=f"{INTERNO}/limen",
            conn=conn,
            store=store,
            lavoro=tmp_path / "import",
            **kw,
        )


async def test_andata_e_ritorno(strato: None, postgres_container: str, tmp_path: Path) -> None:
    cfg, store = _cfg(_container(postgres_container), tmp_path)
    chiave = await _esporta(cfg, store, tmp_path)
    assert chiave == "statico/2026-10-26T14-00-00Z/"
    manifest = json.loads(await store.get(chiave + "manifest.json"))
    assert manifest["righe"] == {
        "public.cell_static_factors": 50,
        "public.flood_hazard_subdiv": 1,
        "public.fire_events": 2,
    }
    assert list(manifest["griglia"]) == [SEED_SMALL_AOI]

    # Un server nuovo: stessa griglia, niente fattori né impronte.
    async with acquire() as conn:
        await conn.execute("TRUNCATE cell_static_factors, flood_hazard_subdiv, fire_events")
        await conn.execute("DELETE FROM dataset_versions WHERE source = 'static_bootstrap'")
    await _importa(cfg, store, tmp_path)

    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM cell_static_factors") == 50
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM cell_static_factors WHERE slope_deg = 12.5 AND s_static = 0.4"
            )
            == 50
        )
        assert await conn.fetchval("SELECT hazard_class FROM flood_hazard_subdiv") == "P3"
        assert await conn.fetchval("SELECT sum(hotspots) FROM fire_events") == 6
        # L'impronta torna: con le sorgenti allo stesso percorso il bootstrap
        # non ricalcola.
        assert (
            await conn.fetchval(
                "SELECT version FROM dataset_versions "
                "WHERE source = 'static_bootstrap' AND dataset = 'dem:it-valle-d-aosta'"
            )
            == "v-dem"
        )

    # Ancora una volta: i fattori ci sono, senza --forza non si toccano.
    with pytest.raises(BackupError, match="già 50 righe"):
        await _importa(cfg, store, tmp_path)
    # Con --forza le impronte di qui descrivono fattori che vanno via: si
    # tolgono, restano quelle dello snapshot (Codex, #333).
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO dataset_versions (source, dataset, version) "
            "VALUES ('static_bootstrap', 'dem:it-valle-d-aosta', 'v-locale')"
        )
    await _importa(cfg, store, tmp_path, forza=True)
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM cell_static_factors") == 50
        versioni = await conn.fetch(
            "SELECT version FROM dataset_versions WHERE source = 'static_bootstrap'"
        )
        assert [r["version"] for r in versioni] == ["v-dem"]


async def test_un_import_fallito_lascia_i_dati_di_prima(
    strato: None, postgres_container: str, tmp_path: Path
) -> None:
    """Codex su #333: il TRUNCATE era confermato prima del caricamento."""
    cfg, store = _cfg(_container(postgres_container), tmp_path)
    chiave = await _esporta(cfg, store, tmp_path)
    # Un manifest che promette righe che il dump non ha: il controllo dentro
    # la transazione fallisce, e la transazione intera torna indietro.
    manifest = json.loads(await store.get(chiave + "manifest.json"))
    manifest["righe"]["public.cell_static_factors"] += 1
    await store.put(chiave + "manifest.json", json.dumps(manifest).encode())
    async with acquire() as conn:
        await conn.execute("UPDATE cell_static_factors SET slope_deg = 7.0")
    with pytest.raises(BackupError, match="righe diverse"):
        await _importa(cfg, store, tmp_path, forza=True)
    async with acquire() as conn:
        rimasti = await conn.fetchval(
            "SELECT count(*) FROM cell_static_factors WHERE slope_deg = 7.0"
        )
        assert rimasti == 50
        assert await conn.fetchval("SELECT count(*) FROM fire_events") == 2
        versione = await conn.fetchval(
            "SELECT version FROM dataset_versions WHERE source = 'static_bootstrap'"
        )
        assert versione == "v-dem"


async def test_una_griglia_diversa_si_rifiuta(
    strato: None, postgres_container: str, tmp_path: Path
) -> None:
    cfg, store = _cfg(_container(postgres_container), tmp_path)
    await _esporta(cfg, store, tmp_path)
    async with acquire() as conn:
        await conn.execute("TRUNCATE cell_static_factors")
        await conn.execute("DELETE FROM grid_cells WHERE id = (SELECT max(id) FROM grid_cells)")
    with pytest.raises(BackupError, match="griglia diversa"):
        await _importa(cfg, store, tmp_path)


async def test_una_migrazione_diversa_si_rifiuta(
    strato: None, postgres_container: str, tmp_path: Path
) -> None:
    cfg, store = _cfg(_container(postgres_container), tmp_path)
    await _esporta(cfg, store, tmp_path)
    async with acquire() as conn:
        await conn.execute("TRUNCATE cell_static_factors")
        await conn.execute(
            "INSERT INTO schema_migrations (name, checksum) VALUES ('999_futuro.sql', 'x')"
        )
    try:
        with pytest.raises(BackupError, match="migrazione 999_futuro"):
            await _importa(cfg, store, tmp_path)
    finally:
        async with acquire() as conn:
            await conn.execute("DELETE FROM schema_migrations WHERE name = '999_futuro.sql'")
