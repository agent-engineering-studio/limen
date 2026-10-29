"""`spesa_llm_repo` contro un PostgreSQL vero: il mese si conta in UTC.

Il tetto del revisore poggia su questa somma. Una riga del mese scorso che
entrasse nel conto lo fermerebbe per niente; una di questo mese che ne
uscisse lo lascerebbe spendere oltre.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from limen.data.db import acquire
from limen.data.repos import spesa_llm_repo

pytestmark = pytest.mark.integration


async def _pulisci() -> None:
    async with acquire() as conn:
        await conn.execute("DELETE FROM spesa_llm")


async def test_la_spesa_del_mese_esclude_il_mese_prima(pg_pool: object) -> None:
    await _pulisci()
    assert await spesa_llm_repo.spesa_del_mese() == Decimal(0)
    for costo in (Decimal("0.012345"), Decimal("1.5")):
        await spesa_llm_repo.registra(
            origine="limen-fedelta-racconti",
            riferimento="msgbatch_1",
            modello="claude-sonnet-5-5",
            input_tokens=6000,
            output_tokens=1200,
            costo_usd=costo,
        )
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO spesa_llm (registrata_at, origine, modello, input_tokens,
                                   output_tokens, costo_usd)
            VALUES (date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
                        - interval '1 second',
                    'limen-fedelta-racconti', 'claude-sonnet-5-5', 1, 1, 99)
            """
        )
    assert await spesa_llm_repo.spesa_del_mese() == Decimal("1.512345")
    await _pulisci()
