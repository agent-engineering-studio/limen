"""La spesa per le chiamate dirette a Claude — migrazione 083."""

from __future__ import annotations

from decimal import Decimal

from limen.data.db import acquire


async def registra(
    *,
    origine: str,
    riferimento: str | None,
    modello: str,
    input_tokens: int,
    output_tokens: int,
    costo_usd: Decimal,
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO spesa_llm
                (origine, riferimento, modello, input_tokens, output_tokens, costo_usd)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            origine,
            riferimento,
            modello,
            input_tokens,
            output_tokens,
            costo_usd,
        )


async def spesa_del_mese() -> Decimal:
    """Il totale del mese solare in corso, in UTC."""
    async with acquire() as conn:
        totale = await conn.fetchval(
            """
            SELECT coalesce(sum(costo_usd), 0)
            FROM spesa_llm
            WHERE registrata_at >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
            """
        )
    return Decimal(totale)
