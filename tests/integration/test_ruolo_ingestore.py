"""L'ingestore dei sensori di terzi scrive con un ruolo che non può altro (#267).

Legge messaggi che chiunque abbia un certificato può aver scritto: un bug nel
parser o nella pipeline non deve arrivare al livello di fiducia di un
dispositivo, ai punteggi o al registro di chi ha registrato i sensori.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from importlib import resources

import asyncpg
import pytest
from pydantic import SecretStr

from limen.data.db import acquire, crea_pool, dsn_con_ruolo, usa_pool
from limen.data.migrate import imposta_password
from limen.integrations.iot.ingestore_v2 import Esito
from tests.integration.test_iot_ingestore_v2 import (
    ADESSO,
    ID,
    TOPIC,
    _cella_e_dispositivo,
    _ingestore,
    _msg,
    _righe,
)

pytestmark = pytest.mark.integration

PASSWORD = "abcdef0123456789abcdef0123456789"


@pytest.fixture
async def pool_ristretto(
    postgres_container: str, pg_pool: asyncpg.Pool
) -> AsyncIterator[asyncpg.Pool]:
    await imposta_password(
        "limen_ingestore",
        SecretStr(PASSWORD),
        variabile="IOT__CITTADINI__DB_PASSWORD",
        obbligatoria=False,
    )
    pool = await crea_pool(
        dsn_con_ruolo(postgres_container, "limen_ingestore", PASSWORD), max_size=2
    )
    try:
        yield pool
    finally:
        await pool.close()


async def test_la_pipeline_salva_col_ruolo_ristretto(
    reset_db: None, pool_ristretto: asyncpg.Pool
) -> None:
    await _cella_e_dispositivo()
    ing = _ingestore()
    with usa_pool(pool_ristretto):
        assert await ing.gestisci(topic=f"limen/v2/{ID}/status", payload=b"online") is Esito.STATO
        assert (
            await ing.gestisci(
                topic=TOPIC,
                payload=_msg(1, ("rainfall", "mm", 0.4, ADESSO - timedelta(minutes=5))),
            )
            is Esito.SALVATO
        )
        # Il replay passa dallo stesso ruolo e si ferma alla sequenza.
        assert (
            await ing.gestisci(
                topic=TOPIC,
                payload=_msg(1, ("rainfall", "mm", 0.4, ADESSO - timedelta(minutes=5))),
            )
            is Esito.SEQUENZA
        )
    assert len(await _righe()) == 1


@pytest.mark.parametrize(
    "sql",
    [
        f"UPDATE sensor_devices SET livello = 2 WHERE id = '{ID}'",
        f"UPDATE sensor_devices SET calibration = '{{}}' WHERE id = '{ID}'",
        "SELECT email FROM sensori_registranti",
        "SELECT registrante_id FROM sensor_devices",
        "DELETE FROM sensor_observations",
        "SELECT count(*) FROM risk_assessments",
        "INSERT INTO alert_dispatches DEFAULT VALUES",
    ],
)
async def test_il_ruolo_ristretto_non_arriva_oltre(
    reset_db: None, pool_ristretto: asyncpg.Pool, sql: str
) -> None:
    await _cella_e_dispositivo()
    async with pool_ristretto.acquire() as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(sql)


async def test_un_ruolo_ristretto_con_privilegi_ferma_la_migrazione(pg_pool: asyncpg.Pool) -> None:
    """Codex, PR #279: i REVOKE della 079 non tolgono SUPERUSER né appartenenze."""
    sql = (
        resources.files("limen.data.migrations")
        .joinpath("079_ruolo_ingestore.sql")
        .read_text(encoding="utf-8")
    )
    async with acquire() as conn:
        await conn.execute("GRANT pg_read_all_data TO limen_ingestore")
        try:
            with pytest.raises(asyncpg.RaiseError, match="limen_ingestore"):
                await conn.execute(sql)
        finally:
            await conn.execute("REVOKE pg_read_all_data FROM limen_ingestore")
        # Pulito, la stessa migrazione si riapplica senza errori.
        await conn.execute(sql)
