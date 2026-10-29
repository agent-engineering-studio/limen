"""Il tetto mensile su Claude, controllato a ogni chiamata (migrazione 083).

Ogni client LLM passa da qui due volte: prima di una chiamata che può finire
su Claude (:func:`verifica`), e dopo ogni chiamata, locale o no, per scriverne
token e costo (:func:`registra`). A tetto raggiunto :func:`verifica` solleva
:class:`BudgetSuperatoError`: i chiamanti la trattano come qualunque guasto del
modello e ripiegano sul testo deterministico, che è l'invariante — mappa e
allerte non dipendono dall'LLM.

Se la spesa non si può leggere la chiamata non parte: un tetto che si apre
quando il database non risponde non è un tetto.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.repos import spesa_llm_repo

log = get_logger(__name__)

# La spesa del mese si rilegge al più ogni mezzo minuto: il briefing fa più
# chiamate in fila, e il costo di una sola è centesimi di dollaro.
_CACHE_SECONDI = 30.0
_cache: tuple[float, Decimal] | None = None


class BudgetSuperatoError(RuntimeError):
    """Il tetto mensile su Claude è raggiunto, o la spesa non si può leggere."""


async def spesa_del_mese() -> Decimal:
    global _cache
    adesso = time.monotonic()
    if _cache is not None and adesso - _cache[0] < _CACHE_SECONDI:
        return _cache[1]
    spesa = await spesa_llm_repo.spesa_del_mese()
    _cache = (adesso, spesa)
    return spesa


async def superato() -> bool:
    return await spesa_del_mese() >= get_settings().llm.anthropic_budget_mensile_usd


async def verifica(modello: str) -> None:
    """Solleva :class:`BudgetSuperatoError` se una chiamata a Claude non deve partire."""
    budget = get_settings().llm.anthropic_budget_mensile_usd
    try:
        spesa = await spesa_del_mese()
    except Exception as exc:
        log.warning("llm.budget_non_verificabile", model=modello, error=type(exc).__name__)
        raise BudgetSuperatoError("spesa del mese non leggibile") from exc
    if spesa >= budget:
        ripresa = spesa_llm_repo.primo_del_mese_prossimo(datetime.now(UTC).date())
        log.warning(
            "llm.budget_superato",
            model=modello,
            spesa_usd=str(spesa),
            budget_usd=str(budget),
            ripresa=ripresa.isoformat(),
        )
        raise BudgetSuperatoError(f"tetto mensile di {budget} $ raggiunto, fino al {ripresa}")


async def registra(
    *,
    origine: str,
    modello: str,
    input_tokens: int,
    output_tokens: int,
    batch: bool = False,
    riferimento: str | None = None,
) -> Decimal:
    """Scrive la chiamata e ne restituisce il costo (zero per un modello locale).

    Un errore qui non fa perdere la risposta, che è già pagata: lo dice il log.
    """
    global _cache
    costo = get_settings().llm.costo_usd(
        modello, input_tokens, output_tokens, batch=batch
    ) or Decimal(0)
    try:
        await spesa_llm_repo.registra(
            origine=origine,
            riferimento=riferimento,
            modello=modello,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            costo_usd=costo,
        )
    except Exception as exc:
        log.warning(
            "llm.spesa_non_registrata",
            model=modello,
            costo_usd=str(costo),
            error=type(exc).__name__,
        )
        return costo
    if _cache is not None:
        _cache = (_cache[0], _cache[1] + costo)
    return costo
