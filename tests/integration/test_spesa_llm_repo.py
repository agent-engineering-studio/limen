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


async def test_i_consumi_si_raggruppano_per_modello_e_per_giorno(pg_pool: object) -> None:
    await _pulisci()
    for modello, ingresso, uscita, costo in (
        ("claude-haiku-5-5", 1000, 200, Decimal("0.0002")),
        ("claude-haiku-5-5", 3000, 100, Decimal("0.00035")),
        ("chat-8b", 500, 50, Decimal(0)),
    ):
        await spesa_llm_repo.registra(
            origine="Briefing",
            riferimento=None,
            modello=modello,
            input_tokens=ingresso,
            output_tokens=uscita,
            costo_usd=costo,
        )
    per_modello = {c.chiave: c for c in await spesa_llm_repo.consumi_del_mese("modello")}
    assert per_modello["claude-haiku-5-5"].richieste == 2
    assert per_modello["claude-haiku-5-5"].input_tokens == 4000
    assert per_modello["claude-haiku-5-5"].costo_usd == Decimal("0.00055")
    assert per_modello["chat-8b"].costo_usd == 0
    [giorno] = await spesa_llm_repo.consumi_del_mese("giorno")
    assert giorno.richieste == 3 and len(giorno.chiave) == 10
    [origine] = await spesa_llm_repo.consumi_del_mese("origine")
    assert origine.chiave == "Briefing"
    await _pulisci()
