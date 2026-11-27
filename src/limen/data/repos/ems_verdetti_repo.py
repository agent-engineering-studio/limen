"""Vaglio radar delle mappe EMS: verdetti, acqua confermata, acqua possibile (#713).

Tre tabelle (migrazione 102) scritte insieme. ``ems_acqua_possibile`` non la
legge nessuna misura: è acqua che il radar vede fuori dalla mappa, da
riguardare, **mai verità**. ``ems_acqua_confermata`` è la verità più solida,
ma solo con ``independent``: una mappa tracciata sullo stesso Sentinel-1
concorda con il radar perché *è* il radar.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations.copernicus_ems.verdetti import (
    CONFERMATA,
    POSSIBILE,
    Rapporto,
    aoi_label,
)

log = get_logger(__name__)


def _j(value: object) -> str | None:
    return None if value is None else json.dumps(value, sort_keys=True)


async def upsert_many(rapporti: Iterable[Rapporto]) -> int:
    """Riscrive il vaglio con i rapporti letti, in una transazione. Rieseguibile.

    I prodotti senza più un rapporto su disco si tolgono, e lo si dice.

    I poligoni di classe di un prodotto riletto si riscrivono da capo: una
    coppia rifatta senza ``candidate`` non deve lasciare quella di prima.
    """
    righe = list(rapporti)
    if not righe:
        return 0
    letti = [f"{r.activation_code}|{r.product}" for r in righe]
    async with acquire() as conn, conn.transaction():
        # Un rapporto sparito dal disco non lascia il suo verdetto di prima:
        # il backtest toglierebbe ancora quella mappa per un «to check» che
        # non esiste più.
        for tabella in ("ems_verdetti", "ems_acqua_possibile", "ems_acqua_confermata"):
            esito = await conn.execute(
                f"DELETE FROM {tabella} WHERE activation_code || '|' || product <> ALL($1::text[])",
                letti,
            )
            tolte = int(esito.split()[-1])
            if tolte:
                log.info("ems_verdetti.rapporti_tolti", tabella=tabella, count=tolte)
        for r in righe:
            q, a = r.qualita, r.accordo
            await conn.execute(
                """
                INSERT INTO ems_verdetti (
                    activation_code, product, aoi_label, mask_id, pair_stem,
                    verdict, reason, flags, measurements, thresholds,
                    gap_hours, resolution_m, agreement_computed, agreement_reason,
                    independent, km2, scores, quality_file, agreement_file,
                    agreement_geojson, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb,
                    $11, $12, $13, $14, $15, $16::jsonb, $17::jsonb, $18, $19, $20, now()
                )
                ON CONFLICT (activation_code, product) DO UPDATE
                SET aoi_label          = EXCLUDED.aoi_label,
                    mask_id            = EXCLUDED.mask_id,
                    pair_stem          = EXCLUDED.pair_stem,
                    verdict            = EXCLUDED.verdict,
                    reason             = EXCLUDED.reason,
                    flags              = EXCLUDED.flags,
                    measurements       = EXCLUDED.measurements,
                    thresholds         = EXCLUDED.thresholds,
                    gap_hours          = EXCLUDED.gap_hours,
                    resolution_m       = EXCLUDED.resolution_m,
                    agreement_computed = EXCLUDED.agreement_computed,
                    agreement_reason   = EXCLUDED.agreement_reason,
                    independent        = EXCLUDED.independent,
                    km2                = EXCLUDED.km2,
                    scores             = EXCLUDED.scores,
                    quality_file       = EXCLUDED.quality_file,
                    agreement_file     = EXCLUDED.agreement_file,
                    agreement_geojson  = EXCLUDED.agreement_geojson,
                    updated_at         = now()
                """,
                r.activation_code,
                r.product,
                aoi_label(r.product),
                r.mask_id,
                r.stem,
                r.verdict,
                q.reason if q else None,
                _j(q.flags if q else []),
                _j(q.measurements if q else {}),
                _j(q.thresholds if q else None),
                q.gap_hours if q else (a.gap_hours if a else None),
                q.resolution_m if q else (a.resolution_m if a else None),
                a.computed if a else None,
                a.reason if a else None,
                r.independent,
                _j(a.km2 if a else None),
                _j(a.scores if a else None),
                q.file if q else None,
                a.file if a else None,
                a.geojson if a else None,
            )
            for tabella in ("ems_acqua_possibile", "ems_acqua_confermata"):
                await conn.execute(
                    f"DELETE FROM {tabella} WHERE activation_code = $1 AND product = $2",
                    r.activation_code,
                    r.product,
                )
            possibile = r.classi.get(POSSIBILE)
            if possibile is not None:
                await conn.execute(
                    """
                    INSERT INTO ems_acqua_possibile
                        (activation_code, product, mask_id, area_km2, geom)
                    VALUES ($1, $2, $3, $4, ST_Multi(ST_SetSRID($5::geometry, 4326)))
                    """,
                    r.activation_code,
                    r.product,
                    r.mask_id,
                    possibile.area_km2,
                    possibile.geom,
                )
            confermata = r.classi.get(CONFERMATA)
            # Senza `independent` noto non si scrive: «confermata» da una mappa
            # di cui non si sa se è il radar stesso non conferma niente.
            if confermata is not None and r.independent is not None:
                await conn.execute(
                    """
                    INSERT INTO ems_acqua_confermata
                        (activation_code, product, mask_id, independent, area_km2, geom)
                    VALUES ($1, $2, $3, $4, $5, ST_Multi(ST_SetSRID($6::geometry, 4326)))
                    """,
                    r.activation_code,
                    r.product,
                    r.mask_id,
                    r.independent,
                    confermata.area_km2,
                    confermata.geom,
                )
    log.info("ems_verdetti.upsert_many", count=len(righe))
    return len(righe)


async def prodotti_ems() -> set[str]:
    """Le maschere di prodotto che Limen conosce: maschere più prefissi dei poligoni."""
    async with acquire() as conn:
        rows = await conn.fetch(
            r"""
            SELECT id AS mask_id FROM flood_observation_masks WHERE source = 'copernicus-ems'
            UNION
            SELECT DISTINCT regexp_replace(id, '-\d+-\d+$', '') FROM flood_events
            WHERE source = 'copernicus-ems'
            """
        )
    return {str(r["mask_id"]) for r in rows}


@dataclass(frozen=True, slots=True)
class VerdettoBacktest:
    """Ciò che il backtest legge di un verdetto."""

    activation_code: str
    product: str
    mask_id: str
    verdict: str | None
    flag_codes: tuple[str, ...]
    independent: bool | None
    #: ``None``: il verdetto viene solo dal rapporto di accordo, flag non letti.
    quality_file: str | None = None


async def per_backtest() -> list[VerdettoBacktest]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT activation_code, product, mask_id, verdict, flags, independent, quality_file
            FROM ems_verdetti
            ORDER BY activation_code, product
            """
        )
    out: list[VerdettoBacktest] = []
    for r in rows:
        flags = r["flags"]
        if isinstance(flags, str):
            flags = json.loads(flags)
        out.append(
            VerdettoBacktest(
                activation_code=str(r["activation_code"]),
                product=str(r["product"]),
                mask_id=str(r["mask_id"]),
                verdict=r["verdict"],
                flag_codes=tuple(str(f.get("code")) for f in flags or [] if f.get("code")),
                independent=r["independent"],
                quality_file=r["quality_file"],
            )
        )
    return out


async def celle_confermate(aoi_id: str) -> dict[str, set[str]]:
    """``{cella: maschere}`` dell'acqua confermata dal radar, **solo mappe indipendenti**."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT g.id AS cell_id, c.mask_id
            FROM ems_acqua_confermata c
            JOIN grid_cells g ON ST_Intersects(g.geom, c.geom)
            WHERE g.aoi_id = $1 AND c.independent
            """,
            aoi_id,
        )
    out: dict[str, set[str]] = {}
    for r in rows:
        out.setdefault(str(r["cell_id"]), set()).add(str(r["mask_id"]))
    return out


__all__ = [
    "VerdettoBacktest",
    "celle_confermate",
    "per_backtest",
    "prodotti_ems",
    "upsert_many",
]
