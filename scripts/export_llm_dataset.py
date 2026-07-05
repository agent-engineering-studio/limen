"""Export (assessment → briefing) pairs as an Alpaca-format SFT dataset.

Builds ``llm-training/datasets/briefing_sft.json`` from the latest stored
briefing per AOI: the model input mirrors the facts the BriefingAgent sees,
the output is the production briefing. Re-run any time to refresh; the file
grows as more (validated) briefings accumulate.

Usage:  uv run python scripts/export_llm_dataset.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from limen.data.db import acquire, lifespan_pool

OUT = Path(__file__).resolve().parent.parent / "llm-training" / "datasets" / "briefing_sft.json"

INSTRUCTION = (
    "Sei Limen Briefing, agente narrativo per il rischio frane sul territorio "
    "italiano. Riassumi la valutazione di rischio fornita in input — già "
    "calcolata da un motore deterministico autorevole — senza alterarla. "
    "Scrivi 150-250 parole in italiano (punta a ~200, mai sotto 160), in prosa "
    "scorrevole senza elenchi, titoli o strutture dati grezze. Non inventare "
    "numeri: usa solo i valori presenti nell'input. Indica la classe di rischio "
    "dominante, la componente che pesa di più, le anomalie principali, le aree "
    "più esposte e l'orizzonte di monitoraggio raccomandato. Registro tecnico "
    "ma chiaro, nessun termine allarmistico, nessun imperativo agli operatori."
)


async def main() -> None:
    async with lifespan_pool():
        async with acquire() as conn:
            aois = await conn.fetch(
                """
                WITH latest AS (
                    SELECT g.aoi_id, MAX(ra.computed_at) AS ts
                    FROM risk_assessments ra JOIN grid_cells g ON g.id = ra.cell_id
                    GROUP BY g.aoi_id
                )
                SELECT l.aoi_id, l.ts FROM latest l ORDER BY l.aoi_id
                """
            )
            examples: list[dict[str, str]] = []
            for a in aois:
                rows = await conn.fetch(
                    """
                    SELECT ra.cell_id, ra.score, ra.class, ra.explanation
                    FROM risk_assessments ra JOIN grid_cells g ON g.id = ra.cell_id
                    WHERE g.aoi_id = $1 AND ra.computed_at = $2
                    ORDER BY ra.score DESC
                    """,
                    a["aoi_id"],
                    a["ts"],
                )
                if not rows:
                    continue
                expl = rows[0]["explanation"]
                expl = json.loads(expl) if isinstance(expl, str) else (expl or {})
                briefing = expl.get("briefing_it")
                if not briefing:
                    continue
                by_level: dict[str, int] = {}
                for r in rows:
                    by_level[str(r["class"])] = by_level.get(str(r["class"]), 0) + 1
                payload = {
                    "aoi_id": str(a["aoi_id"]),
                    "valutato_il": a["ts"].isoformat(),
                    "celle_totali": len(rows),
                    "distribuzione_classi": by_level,
                    "celle_high_o_superiori": by_level.get("High", 0)
                    + by_level.get("VeryHigh", 0),
                    "top_celle": [
                        {
                            "cell_id": str(r["cell_id"]),
                            "score": round(float(r["score"]), 2),
                            "classe": str(r["class"]),
                        }
                        for r in rows[:5]
                    ],
                    "analisi": expl.get("analysis"),
                }
                examples.append(
                    {
                        "instruction": INSTRUCTION,
                        "input": json.dumps(payload, ensure_ascii=False),
                        "output": str(briefing),
                    }
                )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"scritti {len(examples)} esempi -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
