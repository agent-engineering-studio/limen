"""``esposizione_comuni`` (migrazione 085): gli indicatori ISPRA per comune."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ispra_idrogeo.predisposition import SHARES, Kind, rule, step_of

from limen.config.catalogo_dati import carica_catalogo
from limen.data.db import acquire

if TYPE_CHECKING:
    from limen.integrations.idrogeo.esposizione import EsposizioneComune

#: Le colonne che l'API dei comuni espone; `indicatori` resta nel database.
CAMPI_PUBBLICI = (
    "pop_residenti",
    "pop_frana_p3p4",
    "pop_frana_p3p4_pct",
    "pop_idraulica_p2",
    "pop_idraulica_p2_pct",
    "edifici",
    "imprese",
)


async def sostituisci(righe: Sequence[EsposizioneComune], *, version_id: int) -> int:
    """Scrive la fotografia nuova al posto della vecchia, in una transazione.

    Al posto e non sopra: un comune che ISPRA non elenca più (una fusione)
    non deve restare con i numeri di prima.
    """
    async with acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM esposizione_comuni")
        await conn.executemany(
            """
            INSERT INTO esposizione_comuni (
                istat_code, nome, pop_residenti, pop_frana_p3p4, pop_frana_p3p4_pct,
                pop_idraulica_p2, pop_idraulica_p2_pct, edifici, imprese,
                indicatori, dataset_version_id, aggiornato
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, now())
            """,
            [
                (
                    r.istat_code,
                    r.nome,
                    r.pop_residenti,
                    r.pop_frana_p3p4,
                    r.pop_frana_p3p4_pct,
                    r.pop_idraulica_p2,
                    r.pop_idraulica_p2_pct,
                    r.edifici,
                    r.imprese,
                    json.dumps(r.indicatori),
                    version_id,
                )
                for r in righe
            ],
        )
    return len(righe)


#: Il nome di Limen per i due tipi della libreria.
_TIPI: dict[str, Kind] = {"frana": "landslide", "alluvione": "flood"}


def predisposizione(indicatori: dict[str, Any]) -> dict[str, Any] | None:
    """Le due classi ufficiali di predisposizione del comune (#672), da ``indicatori``.

    Quota del territorio in pericolosità frana P3+P4 (mosaico 2024) e in
    scenario idraulico P2, in cinque passi a soglie fisse. Non usa la pioggia:
    non è un'allerta, e non entra nel punteggio.
    """
    out: dict[str, Any] = {}
    for nome, tipo in _TIPI.items():
        valore = indicatori.get(SHARES[tipo][0])
        quota = float(valore) if isinstance(valore, int | float) and valore >= 0 else None
        out[nome] = {"classe": step_of(quota), "quota_pct": quota}
    if all(v["classe"] is None for v in out.values()):
        return None
    return {**out, "regola": rule()}


async def per_comuni(conn: Any, istat_codes: Sequence[str]) -> dict[str, dict[str, Any]]:
    """I campi pubblici dei comuni chiesti; un comune senza riga non c'è."""
    if not istat_codes:
        return {}
    rows = await conn.fetch(
        f"SELECT istat_code, {', '.join(CAMPI_PUBBLICI)}, aggiornato, "
        "jsonb_build_object("
        + ", ".join(f"'{SHARES[t][0]}', indicatori->'{SHARES[t][0]}'" for t in _TIPI.values())
        + ") AS quote "
        "FROM esposizione_comuni WHERE istat_code = ANY($1::text[])",
        list(istat_codes),
    )
    voce = carica_catalogo().voce("pir_comuni")
    return {
        str(r["istat_code"]): {
            **{c: r[c] for c in CAMPI_PUBBLICI},
            "aggiornato": r["aggiornato"].isoformat(),
            "predisposizione": predisposizione(_json(r["quote"])),
            # La citazione che la CC BY 4.0 chiede, dalla voce del catalogo (#666).
            "dataset": voce.id,
            "licenza": voce.licenza,
            "attribuzione": voce.attribuzione,
        }
        for r in rows
    }


def _json(valore: Any) -> dict[str, Any]:
    letto = json.loads(valore) if isinstance(valore, str) else valore
    return letto if isinstance(letto, dict) else {}


__all__ = ["CAMPI_PUBBLICI", "per_comuni", "predisposizione", "sostituisci"]
