"""Il registro delle verifiche (migrazione 074): ogni evento verificato, con la
misura di Limen congelata prima che la retention la cancelli."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shapely.geometry import Point

from limen.core.models.hazard import HazardType
from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class VerificaEvento:
    slug: str
    hazard: HazardType
    esito: str
    evento_at: datetime
    precisione_ora: str
    luogo: str
    comuni: tuple[str, ...]
    misura: dict[str, Any]
    motivo: str | None = None
    regione: str | None = None
    punto: Point | None = None
    precisione_luogo: str | None = None
    fonti: tuple[dict[str, Any], ...] = ()


async def upsert(v: VerificaEvento) -> tuple[Point, str] | None:
    """Scrive o aggiorna la verifica; restituisce il punto registrato e la sua
    precisione.

    Senza un punto dalla notizia vale il centroide dei comuni, a precisione
    P10 per un comune e P100 per più d'uno: è quello che ITALICA scrive per un
    evento localizzato al solo comune. Un comune fuori copertura lascia il
    punto vuoto.
    """
    m = v.misura
    precisione = v.precisione_luogo
    if v.punto is None:
        precisione = "P10" if len(v.comuni) == 1 else "P100"
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH p AS (
                SELECT COALESCE(
                    ST_SetSRID($10::geometry, 4326),
                    (SELECT ST_Centroid(ST_Collect(centroid)) FROM comuni
                     WHERE istat_code = ANY($9))
                ) AS g
            )
            INSERT INTO verifiche_eventi (
                slug, hazard_type, esito, motivo, evento_at, precisione_ora,
                luogo, regione, comuni, geom, precisione_luogo, fonti,
                anticipo_ore_moderato, anticipo_ore_alto, classe_prevista_max,
                fondo_classe_max, adesso_classe_max, misura
            )
            SELECT $1, $2::hazard_type, $3, $4, $5, $6, $7, $8, $9,
                   p.g, CASE WHEN p.g IS NULL THEN NULL ELSE $11 END, $12::jsonb,
                   $13, $14, $15, $16, $17, $18::jsonb
            FROM p
            ON CONFLICT (slug) DO UPDATE
            SET hazard_type           = EXCLUDED.hazard_type,
                esito                 = EXCLUDED.esito,
                motivo                = EXCLUDED.motivo,
                evento_at             = EXCLUDED.evento_at,
                precisione_ora        = EXCLUDED.precisione_ora,
                luogo                 = EXCLUDED.luogo,
                regione               = EXCLUDED.regione,
                comuni                = EXCLUDED.comuni,
                geom                  = EXCLUDED.geom,
                precisione_luogo      = EXCLUDED.precisione_luogo,
                fonti                 = EXCLUDED.fonti,
                anticipo_ore_moderato = EXCLUDED.anticipo_ore_moderato,
                anticipo_ore_alto     = EXCLUDED.anticipo_ore_alto,
                classe_prevista_max   = EXCLUDED.classe_prevista_max,
                fondo_classe_max      = EXCLUDED.fondo_classe_max,
                adesso_classe_max     = EXCLUDED.adesso_classe_max,
                misura                = EXCLUDED.misura,
                aggiornato_at         = now()
            RETURNING geom, precisione_luogo
            """,
            v.slug,
            v.hazard.value,
            v.esito,
            v.motivo,
            v.evento_at,
            v.precisione_ora,
            v.luogo,
            v.regione,
            list(v.comuni),
            v.punto,
            precisione,
            json.dumps(list(v.fonti)),
            m.get("anticipo_ore_moderato"),
            m.get("anticipo_ore_alto"),
            m.get("classe_prevista_max"),
            m.get("fondo_classe_max"),
            m.get("adesso_classe_max"),
            json.dumps(m, default=str),
        )
    if row is None or not isinstance(row["geom"], Point):
        return None
    return row["geom"], str(row["precisione_luogo"])


async def count_by_esito() -> dict[str, int]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT esito, count(*)::int AS n FROM verifiche_eventi GROUP BY 1")
    return {str(r["esito"]): int(r["n"]) for r in rows}


@dataclass(frozen=True, slots=True)
class RigaVerifica:
    """Una verifica come la legge il report: le colonne, non la misura intera."""

    slug: str
    hazard: HazardType
    esito: str
    evento_at: datetime
    luogo: str
    anticipo_ore_moderato: int | None
    anticipo_ore_alto: int | None
    classe_prevista_max: str | None
    fondo_classe_max: str | None
    fondo_giorni_moderato: int | None


async def elenca(*, dal: datetime | None = None, al: datetime | None = None) -> list[RigaVerifica]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT slug, hazard_type::text AS hazard, esito, evento_at, luogo,
                   anticipo_ore_moderato, anticipo_ore_alto, classe_prevista_max,
                   fondo_classe_max, (misura->>'fondo_giorni_moderato')::int AS fondo_giorni
            FROM verifiche_eventi
            WHERE ($1::timestamptz IS NULL OR evento_at >= $1)
              AND ($2::timestamptz IS NULL OR evento_at <= $2)
            ORDER BY hazard_type, evento_at
            """,
            dal,
            al,
        )
    return [
        RigaVerifica(
            slug=str(r["slug"]),
            hazard=HazardType(r["hazard"]),
            esito=str(r["esito"]),
            evento_at=r["evento_at"],
            luogo=str(r["luogo"]),
            anticipo_ore_moderato=r["anticipo_ore_moderato"],
            anticipo_ore_alto=r["anticipo_ore_alto"],
            classe_prevista_max=r["classe_prevista_max"],
            fondo_classe_max=r["fondo_classe_max"],
            fondo_giorni_moderato=r["fondo_giorni"],
        )
        for r in rows
    ]
