"""Le regioni da monitorare: un riassunto per regione, su tutti i pericoli.

La pagina che lo mostra mette accanto ai numeri la spiegazione dell'AI, ma
l'**ordine** delle regioni lo decidono i numeri: celle in classe alta, picco
previsto, comuni coinvolti. L'AI racconta una regione, non la sceglie.
"""

from __future__ import annotations

import json
from typing import Any

from limen.data.db import acquire

_RANGO = {"None": 0, "Low": 1, "Moderate": 2, "High": 3, "VeryHigh": 4}

_REGIONI = """
SELECT a.id, a.name,
       ST_AsGeoJSON(ST_SimplifyPreserveTopology(a.geom, 0.02), 3) AS geom,
       ST_X(ST_PointOnSurface(a.geom)) AS lon,
       ST_Y(ST_PointOnSurface(a.geom)) AS lat
FROM aoi a
WHERE a.kind = 'region'
"""

#: Adesso, per regione e pericolo: solo le celle misurate, perché «non so» non
#: è «tranquillo».
_ADESSO = """
SELECT g.aoi_id, lr.hazard_type::text AS hazard,
       count(*) FILTER (WHERE lr.class IN ('High', 'VeryHigh')) AS alte,
       count(*) FILTER (WHERE lr.class = 'Moderate')             AS moderate,
       max(lr.score)                                              AS max_score,
       (array_agg(lr.class ORDER BY lr.score DESC))[1]            AS classe
FROM latest_risk lr
JOIN grid_cells g ON g.id = lr.cell_id
WHERE COALESCE(lr.measured, true) AND lr.score IS NOT NULL
GROUP BY 1, 2
"""

#: Il picco previsto per regione e pericolo, e quando.
_PREVISTO = """
SELECT DISTINCT ON (g.aoi_id, lf.hazard_type)
       g.aoi_id, lf.hazard_type::text AS hazard, lf.score, lf.class, lf.target_at
FROM latest_forecast lf
JOIN grid_cells g ON g.id = lf.cell_id
WHERE lf.target_at > now()
ORDER BY g.aoi_id, lf.hazard_type, lf.score DESC
"""

#: I tre comuni con la cella peggiore in classe alta, per regione.
_COMUNI = """
WITH c AS (
    SELECT cc.istat_code,
           max(lr.score) AS score,
           (array_agg(lr.hazard_type::text ORDER BY lr.score DESC))[1] AS hazard,
           count(*) AS alte
    FROM latest_risk lr
    JOIN cell_comune_tutte cc ON cc.cell_id = lr.cell_id
    WHERE COALESCE(lr.measured, true) AND lr.class IN ('High', 'VeryHigh')
    GROUP BY 1
), r AS (
    SELECT co.aoi_id, co.istat_code, co.name, c.score, c.hazard, c.alte,
           row_number() OVER (PARTITION BY co.aoi_id ORDER BY c.score DESC, co.name) AS rk
    FROM c JOIN comuni co USING (istat_code)
)
SELECT aoi_id, istat_code, name, score, hazard, alte FROM r WHERE rk <= 3
ORDER BY aoi_id, rk
"""

#: L'allerta ufficiale più alta fra le zone che toccano la regione.
_ALLERTE = """
SELECT a.id AS aoi_id,
       max(d.livello) FILTER (WHERE d.valido = (now() AT TIME ZONE 'Europe/Rome')::date)
           AS oggi,
       max(d.livello) FILTER (WHERE d.valido = (now() AT TIME ZONE 'Europe/Rome')::date + 1)
           AS domani
FROM aoi a
JOIN dpc_allerte d ON ST_Intersects(d.geom, a.geom)
WHERE a.kind = 'region'
  AND d.valido BETWEEN (now() AT TIME ZONE 'Europe/Rome')::date
                   AND (now() AT TIME ZONE 'Europe/Rome')::date + 1
GROUP BY 1
"""

_SPIEGAZIONI = """
SELECT aoi_id, hazard_type::text AS hazard, testo, modello, scritta, livello, analisi
FROM spiegazioni_regione
WHERE NOT ripiego
"""


def _json(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


async def monitoraggio() -> list[dict[str, Any]]:
    """Le regioni, dalla più da guardare alla più tranquilla."""
    async with acquire() as conn:
        regioni = await conn.fetch(_REGIONI)
        adesso = await conn.fetch(_ADESSO)
        previsto = await conn.fetch(_PREVISTO)
        comuni = await conn.fetch(_COMUNI)
        allerte = await conn.fetch(_ALLERTE)
        spiegazioni = await conn.fetch(_SPIEGAZIONI)

    out: dict[str, dict[str, Any]] = {
        str(r["id"]): {
            "aoi_id": str(r["id"]),
            "nome": str(r["name"]),
            "lon": float(r["lon"]),
            "lat": float(r["lat"]),
            "geom": _json(r["geom"]),
            "pericoli": {},
            "previsto": {},
            "comuni": [],
            "allerta": None,
            "spiegazioni": {},
        }
        for r in regioni
    }
    for r in adesso:
        if (reg := out.get(str(r["aoi_id"]))) is not None:
            reg["pericoli"][r["hazard"]] = {
                "alte": int(r["alte"]),
                "moderate": int(r["moderate"]),
                "max_score": round(float(r["max_score"]), 3),
                "classe": str(r["classe"]),
            }
    for r in previsto:
        if (reg := out.get(str(r["aoi_id"]))) is not None:
            reg["previsto"][r["hazard"]] = {
                "score": round(float(r["score"]), 3),
                "classe": str(r["class"]),
                "target_at": r["target_at"].isoformat(),
            }
    for r in comuni:
        if (reg := out.get(str(r["aoi_id"]))) is not None:
            reg["comuni"].append(
                {
                    "istat_code": str(r["istat_code"]),
                    "nome": str(r["name"]),
                    "hazard": str(r["hazard"]),
                    "score": round(float(r["score"]), 3),
                    "celle_alte": int(r["alte"]),
                }
            )
    for r in allerte:
        if (reg := out.get(str(r["aoi_id"]))) is not None:
            reg["allerta"] = {"oggi": r["oggi"], "domani": r["domani"]}
    for r in spiegazioni:
        if (reg := out.get(str(r["aoi_id"]))) is not None:
            reg["spiegazioni"][r["hazard"]] = {
                "testo": str(r["testo"]),
                "modello": str(r["modello"]),
                "scritta": r["scritta"].isoformat(),
                "livello": str(r["livello"]),
                "analisi": _json(r["analisi"]),
            }

    for reg in out.values():
        reg["peggiore"] = _peggiore(reg)
    return sorted(out.values(), key=_ordine)


def _peggiore(reg: dict[str, Any]) -> dict[str, Any] | None:
    """Il pericolo da guardare per primo: la classe più alta, adesso o prevista."""
    candidati: list[tuple[int, float, str, str, bool]] = []
    for hazard, p in reg["pericoli"].items():
        candidati.append((_RANGO.get(p["classe"], 0), p["max_score"], hazard, p["classe"], False))
    for hazard, p in reg["previsto"].items():
        candidati.append((_RANGO.get(p["classe"], 0), p["score"], hazard, p["classe"], True))
    if not candidati:
        return None
    rango, score, hazard, classe, futuro = max(candidati)
    return {"hazard": hazard, "classe": classe, "score": score, "previsto": futuro, "rango": rango}


def _ordine(reg: dict[str, Any]) -> tuple[int, int, float, str]:
    p = reg["peggiore"]
    alte = sum(v["alte"] for v in reg["pericoli"].values())
    return (-(p["rango"] if p else -1), -alte, -(p["score"] if p else 0.0), reg["nome"])


__all__ = ["monitoraggio"]
