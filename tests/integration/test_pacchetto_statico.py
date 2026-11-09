"""Pacchetto rapido (#406): export in tre licenze e import su un server nuovo."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from limen.cli.seed import run as run_seed
from limen.config.catalogo_dati import carica_catalogo
from limen.data.backup import BackupError
from limen.data.db import acquire
from limen.data.pacchetto_statico import (
    TABELLA,
    esporta_pacchetto,
    importa_pacchetto,
    non_assegnate,
)
from tests.conftest import SEED_SMALL_AOI

pytestmark = pytest.mark.integration

ADESSO = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


@pytest.fixture
async def strato(reset_db: None) -> AsyncIterator[None]:
    """Un'AOI con fattori di tutte e tre le licenze, una colonna esclusa e le impronte."""
    await run_seed(only=[SEED_SMALL_AOI])
    async with acquire() as conn:
        await conn.execute("TRUNCATE fire_events")
        await conn.execute(
            """
            INSERT INTO fire_events (cell_id, event_date, hotspots, sources)
            SELECT id, DATE '2024-08-10', 3, ARRAY['VIIRS'] FROM grid_cells ORDER BY id LIMIT 2
            """
        )
        await conn.execute(
            """
            INSERT INTO cell_static_factors
                (cell_id, slope_deg, landuse_code, pai_class_norm, distance_to_road_m,
                 litho_weight, s_static)
            SELECT id, 12.5, '311', 0.6, 420.0, 0.7, 0.4 FROM grid_cells ORDER BY id LIMIT 50
            """
        )
        await conn.executemany(
            "INSERT INTO dataset_versions (source, dataset, version, metadata) "
            "VALUES ('static_bootstrap', $1, $2, '{}')",
            [
                (f"dem:{SEED_SMALL_AOI}", "v-dem"),
                (f"pai:{SEED_SMALL_AOI}", "v-pai"),
                (f"geological:{SEED_SMALL_AOI}", "v-geo"),
            ],
        )
    yield
    async with acquire() as conn:
        await conn.execute("TRUNCATE fire_events")


async def test_ogni_colonna_dello_schema_ha_una_licenza(reset_db: None) -> None:
    async with acquire() as conn:
        colonne = [
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'cell_static_factors'"
            )
        ]
    assert non_assegnate(colonne) == []


async def _esporta(uscita: Path) -> dict[str, Any]:
    async with acquire() as conn:
        return await esporta_pacchetto(
            conn=conn, catalogo=carica_catalogo(), uscita=uscita, adesso=ADESSO
        )


async def test_andata_e_ritorno(strato: None, tmp_path: Path) -> None:
    uscita = tmp_path / "pacchetto"
    manifest = await _esporta(uscita)
    nomi = sorted(p.name for p in uscita.iterdir())
    assert nomi == [
        "ATTRIBUZIONI-cc-by.txt",
        "ATTRIBUZIONI-ispra-by-sa.txt",
        "ATTRIBUZIONI-osm-odbl.txt",
        "catalogo-dcat-ap_it.ttl",
        "cc-by.cell_static_factors.csv.gz",
        "cc-by.fire_events.csv.gz",
        "ispra-by-sa.cell_static_factors.csv.gz",
        "manifest.json",
        "osm-odbl.cell_static_factors.csv.gz",
    ]
    assert json.loads((uscita / "manifest.json").read_text())["licenze"] == manifest["licenze"]
    assert manifest["metadati"] == {"dcat-ap_it": "catalogo-dcat-ap_it.ttl"}
    dcat = (uscita / "catalogo-dcat-ap_it.ttl").read_text()
    # Le distribuzioni portano lo SHA-256 del manifest, non uno calcolato a parte.
    sha = manifest["file"]["osm-odbl.cell_static_factors.csv.gz"]["sha256"]
    assert f'spdx:checksumValue "{sha}"' in dcat

    # Un server nuovo: stessa griglia, niente fattori né impronte.
    async with acquire() as conn:
        await conn.execute("TRUNCATE cell_static_factors, fire_events")
        await conn.execute("DELETE FROM dataset_versions WHERE source = 'static_bootstrap'")
        righe = await importa_pacchetto(conn=conn, cartella=uscita)
        assert righe[TABELLA] == 50
        fattori = await conn.fetchrow(
            "SELECT count(*) FILTER (WHERE slope_deg = 12.5 AND landuse_code = '311' "
            "AND pai_class_norm = 0.6 AND distance_to_road_m = 420.0) AS pieni, "
            "count(litho_weight) AS lito, count(s_static) AS s FROM cell_static_factors"
        )
        assert dict(fattori) == {"pieni": 50, "lito": 0, "s": 0}
        assert await conn.fetchval("SELECT sum(hotspots) FROM fire_events") == 6
        # Tornano le impronte dei passi inclusi, non quella della litologia: il
        # bootstrap che segue ricalcola solo quel passo.
        versioni = {
            r["dataset"].split(":")[0]: r["version"]
            for r in await conn.fetch(
                "SELECT dataset, version FROM dataset_versions WHERE source = 'static_bootstrap'"
            )
        }
        assert versioni == {"dem": "v-dem", "pai": "v-pai"}

        with pytest.raises(BackupError, match="già 50 righe"):
            await importa_pacchetto(conn=conn, cartella=uscita)
        await importa_pacchetto(conn=conn, cartella=uscita, forza=True)
        assert await conn.fetchval("SELECT count(*) FROM cell_static_factors") == 50


async def test_un_file_alterato_non_tocca_niente(strato: None, tmp_path: Path) -> None:
    uscita = tmp_path / "pacchetto"
    await _esporta(uscita)
    (uscita / "osm-odbl.cell_static_factors.csv.gz").write_bytes(b"non gzip")
    async with acquire() as conn:
        with pytest.raises(BackupError, match="sha256"):
            await importa_pacchetto(conn=conn, cartella=uscita, forza=True)
        assert await conn.fetchval("SELECT count(litho_weight) FROM cell_static_factors") == 50


async def test_una_griglia_diversa_si_rifiuta(strato: None, tmp_path: Path) -> None:
    uscita = tmp_path / "pacchetto"
    await _esporta(uscita)
    manifest = json.loads((uscita / "manifest.json").read_text())
    manifest["griglia"][SEED_SMALL_AOI]["celle"] += 1
    (uscita / "manifest.json").write_text(json.dumps(manifest))
    async with acquire() as conn:
        with pytest.raises(BackupError, match="griglia diversa"):
            await importa_pacchetto(conn=conn, cartella=uscita, forza=True)
