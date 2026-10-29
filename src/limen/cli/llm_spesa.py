"""``limen llm-spesa`` — quanto ha speso Limen su Claude questo mese.

La spesa in dollari sta qui e nei log, non sul sito: la pagina pubblica
mostra solo i token (`GET /api/status/llm`).
"""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import spesa_llm_repo


async def run() -> int:
    budget = get_settings().llm.anthropic_budget_mensile_usd
    async with lifespan_pool():
        await run_migrations()
        spesa = await spesa_llm_repo.spesa_del_mese()
        per_origine = await spesa_llm_repo.consumi_del_mese("origine")
        per_modello = await spesa_llm_repo.consumi_del_mese("modello")
    stato = "IN PAUSA" if spesa >= budget else "attivo"
    print(f"spesa del mese: {spesa:.4f} $ su {budget} $ ({stato})")
    for titolo, righe in (("per origine", per_origine), ("per modello", per_modello)):
        print(f"\n{titolo}:")
        for r in righe:
            print(
                f"  {r.chiave:28} {r.richieste:6} rich.  {r.input_tokens:>10} in  "
                f"{r.output_tokens:>10} out  {r.costo_usd:>10.4f} $"
            )
    return 0
