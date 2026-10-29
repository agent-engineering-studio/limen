"""Token e spesa di ogni chiamata LLM — migrazione 083."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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


_DEL_MESE = "registrata_at >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"


@dataclass(frozen=True, slots=True)
class Consumo:
    """Token e richieste di un gruppo (un giorno, un modello, un'origine)."""

    chiave: str
    richieste: int
    input_tokens: int
    output_tokens: int
    costo_usd: Decimal


async def consumi_del_mese(per: str) -> list[Consumo]:
    """Il mese in corso raggruppato per ``giorno``, ``modello`` o ``origine``."""
    colonna = {
        "giorno": "to_char(registrata_at AT TIME ZONE 'UTC', 'YYYY-MM-DD')",
        "modello": "modello",
        "origine": "origine",
    }[per]
    async with acquire() as conn:
        righe = await conn.fetch(
            f"""
            SELECT {colonna} AS chiave, count(*) AS richieste,
                   coalesce(sum(input_tokens), 0) AS input_tokens,
                   coalesce(sum(output_tokens), 0) AS output_tokens,
                   coalesce(sum(costo_usd), 0) AS costo_usd
            FROM spesa_llm
            WHERE {_DEL_MESE}
            GROUP BY 1
            ORDER BY 1
            """
        )
    return [
        Consumo(
            chiave=r["chiave"],
            richieste=r["richieste"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            costo_usd=Decimal(r["costo_usd"]),
        )
        for r in righe
    ]


def primo_del_mese_prossimo(oggi: date) -> date:
    return date(oggi.year + oggi.month // 12, oggi.month % 12 + 1, 1)
