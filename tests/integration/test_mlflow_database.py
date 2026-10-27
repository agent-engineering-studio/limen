"""Il database del registry MLflow nasce con le migrazioni, non solo con initdb (#327)."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

from limen.config.settings import Settings
from limen.data.db import acquire
from limen.data.migrate import crea_database_mlflow

pytestmark = pytest.mark.integration

NOME = "mlflow_prova_327"


def _settings(dsn: str, tracking: str) -> Settings:
    return Settings.model_validate(
        {"db": {"connection_string": dsn}, "scoring": {"mlflow_tracking_uri": tracking}}
    )


async def _esiste(nome: str) -> bool:
    async with acquire() as conn:
        return bool(await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", nome))


async def test_crea_il_database_se_manca_e_poi_non_lo_tocca(
    pg_pool: asyncpg.Pool, postgres_container: str
) -> None:
    parti = urlsplit(postgres_container)
    tracking = urlunsplit(parti._replace(scheme="postgresql+psycopg2", path=f"/{NOME}"))
    settings = _settings(postgres_container, tracking)
    try:
        await crea_database_mlflow(settings)
        assert await _esiste(NOME)
        # Idempotente: il secondo avvio lo trova e non solleva.
        await crea_database_mlflow(settings)
        assert await _esiste(NOME)
    finally:
        async with acquire() as conn:
            await conn.execute(f"DROP DATABASE IF EXISTS {NOME}")


async def test_un_registry_altrove_non_si_crea(
    pg_pool: asyncpg.Pool, postgres_container: str
) -> None:
    for tracking in ("sqlite:///mlflow.db", f"postgresql://u:p@altrove:5432/{NOME}"):
        await crea_database_mlflow(_settings(postgres_container, tracking))
    assert not await _esiste(NOME)
