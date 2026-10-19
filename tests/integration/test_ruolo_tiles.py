"""pg_tileserv pubblica solo ciò che la mappa disegna (#269).

pg_tileserv non ha un elenco di layer: pubblica ogni tabella con geometria
che il suo ruolo legge e ogni funzione `(z, x, y, ...) -> bytea` che esegue.
Questi test rifanno la sua scoperta per `limen_tiles` e fissano il risultato:
un layer nuovo deve entrare qui, apposta.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from pydantic import SecretStr

from limen.data.db import acquire
from limen.data.migrate import imposta_password

pytestmark = pytest.mark.integration

PUBBLICATI = {
    "public.v_risk_tiles",
    "public.v_region_tiles",
    "public.v_comune_tiles",
    "public.v_multi_hazard",
    "public.v_dpc_allerte_oggi",
    "public.v_shadow_divergence_tiles",
    "public.fire_perimeters",
    "public.flood_events",
    "public.flood_hazard_subdiv",
    "public.risk_at",
    "public.multi_hazard_at",
    "public.forecast_at",
}

# Le stesse condizioni delle query di catalogo di pg_tileserv
# (layer_table.go, layer_function.go), con il ruolo esplicito.
_TABELLE = """
SELECT DISTINCT n.nspname || '.' || c.relname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
JOIN pg_type t ON t.oid = a.atttypid
WHERE c.relkind IN ('r', 'v', 'm', 'p', 'f')
  AND t.typname IN ('geometry', 'geography')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND has_schema_privilege('limen_tiles', n.oid, 'USAGE')
  AND has_table_privilege('limen_tiles', c.oid, 'SELECT')
"""

_FUNZIONI = """
SELECT n.nspname || '.' || p.proname
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE p.prorettype = 'bytea'::regtype
  AND p.proargnames[1:3] = ARRAY['z', 'x', 'y']
  AND p.proargtypes[0] = 'int4'::regtype
  AND p.proargtypes[1] = 'int4'::regtype
  AND p.proargtypes[2] = 'int4'::regtype
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND has_schema_privilege('limen_tiles', n.oid, 'USAGE')
  AND has_function_privilege('limen_tiles', p.oid, 'EXECUTE')
"""


async def test_pg_tileserv_vede_solo_i_layer_della_mappa(pg_pool: asyncpg.Pool) -> None:
    async with acquire() as conn:
        tabelle = {r[0] for r in await conn.fetch(_TABELLE)}
        funzioni = {r[0] for r in await conn.fetch(_FUNZIONI)}

    assert tabelle | funzioni == PUBBLICATI
    assert "public.sensor_devices" not in tabelle


async def test_le_tile_rispondono_con_il_ruolo_ristretto(pg_pool: asyncpg.Pool) -> None:
    async with acquire() as conn, conn.transaction():
        await conn.execute("SET LOCAL ROLE limen_tiles")
        for layer in sorted(PUBBLICATI):
            if layer.endswith("_at"):
                continue
            await conn.fetch(f"SELECT * FROM {layer} LIMIT 1")
        await conn.fetchval("SELECT public.risk_at(9, 273, 190, 0, 'flood')")
        await conn.fetchval("SELECT public.multi_hazard_at(9, 273, 190)")
        await conn.fetchval("SELECT public.forecast_at(9, 273, 190, 24, NULL)")


async def test_le_tabelle_grezze_restano_chiuse(pg_pool: asyncpg.Pool) -> None:
    async with acquire() as conn:
        for tabella in ("sensor_devices", "grid_cells", "sensori_registranti"):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with conn.transaction():
                    await conn.execute("SET LOCAL ROLE limen_tiles")
                    await conn.fetch(f"SELECT 1 FROM {tabella} LIMIT 1")


async def test_la_password_viene_dal_env(postgres_container: str, pg_pool: asyncpg.Pool) -> None:
    password = "0123456789abcdef0123456789abcdef"
    await imposta_password(
        "limen_tiles", SecretStr(password), variabile="DB__TILES_PASSWORD", obbligatoria=True
    )

    parti = urlsplit(postgres_container)
    netloc = f"limen_tiles:{password}@{parti.hostname}:{parti.port}"
    conn = await asyncpg.connect(urlunsplit(parti._replace(netloc=netloc)))
    try:
        assert await conn.fetchval("SELECT current_user") == "limen_tiles"
    finally:
        await conn.close()


async def test_le_funzioni_delle_tile_restano_security_definer(pg_pool: asyncpg.Pool) -> None:
    # `CREATE OR REPLACE` le riporta INVOKER: la tile risponderebbe
    # «permission denied» solo quando pg_tileserv la chiama.
    async with acquire() as conn:
        tornate_invoker = await conn.fetch(
            """
            SELECT proname FROM pg_proc
            WHERE proname IN ('risk_at', 'multi_hazard_at', 'forecast_at')
              AND (NOT prosecdef
                   OR NOT 'search_path=public, pg_temp' = ANY(coalesce(proconfig, '{}')))
            """
        )
    assert tornate_invoker == []


async def test_una_password_che_romperebbe_l_url_non_si_imposta(
    postgres_container: str, pg_pool: asyncpg.Pool
) -> None:
    await imposta_password(
        "limen_tiles",
        SecretStr("a@b/c:" + "0" * 32),
        variabile="DB__TILES_PASSWORD",
        obbligatoria=True,
    )

    parti = urlsplit(postgres_container)
    netloc = f"limen_tiles:a%40b%2Fc%3A{'0' * 32}@{parti.hostname}:{parti.port}"
    with pytest.raises(asyncpg.InvalidPasswordError):
        await asyncpg.connect(urlunsplit(parti._replace(netloc=netloc)))
