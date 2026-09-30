"""Letture su `mv_comune_risk`: la classifica e il dettaglio di un comune.

Dalla migrazione 051 il rollup ha una riga per **(comune, pericolo)**, e
queste query ne ricompongono una per comune con i tre indicatori affiancati:
è la forma che la colonna della dashboard disegna, e farla qui evita alla
pagina tre richieste per dire una riga.
"""

from __future__ import annotations

import json
from typing import Any

from limen.core.cascades.attention import HazardStanding, attention_index
from limen.core.cascades.config import load_cascades
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire

#: Ordine delle classi, per scegliere il peggiore fra i pericoli. In SQL
#: perché è lì che si ordina: portarlo in Python vorrebbe dire leggere tutti
#: i comuni per mostrarne cinquanta.
_RANK = """
    CASE worst_class
        WHEN 'VeryHigh' THEN 4
        WHEN 'High'     THEN 3
        WHEN 'Moderate' THEN 2
        WHEN 'Low'      THEN 1
        ELSE 0
    END
"""

#: Una riga per comune: i tre pericoli in un oggetto, più il peggiore
#: ricomposto per l'ordinamento e per i consumatori che leggevano la forma
#: a pericolo unico.
_PER_COMUNE = f"""
SELECT
    istat_code,
    name,
    aoi_id,
    jsonb_object_agg(
        hazard_type::text,
        jsonb_build_object(
            'class',    worst_class,
            'score',    round(COALESCE(max_score, 0)::numeric, 3),
            'priority', round(COALESCE(priority, 0)::numeric, 3),
            'n_cells',  n_cells,
            'n_alert',  n_alert,
            'measured', measured
        )
    ) AS hazards,
    -- Il peggiore fra i pericoli: è ciò che ordina la classifica e ciò che
    -- i consumatori a pericolo unico leggevano come `worst_class`.
    (array_agg(hazard_type::text ORDER BY {_RANK} DESC, max_score DESC NULLS LAST,
               hazard_type::text))[1] AS worst_hazard,
    (array_agg(worst_class ORDER BY {_RANK} DESC, max_score DESC NULLS LAST,
               hazard_type::text))[1] AS worst_class,
    max(COALESCE(max_score, 0))            AS max_score,
    max({_RANK})                           AS worst_rank,
    max(n_cells)                           AS n_cells,
    sum(n_alert)                           AS n_alert,
    sum(n_none)                            AS n_none,
    sum(n_low)                             AS n_low,
    sum(n_moderate)                        AS n_moderate,
    sum(n_high)                            AS n_high,
    sum(n_veryhigh)                        AS n_veryhigh,
    max(exposure_rank)                     AS exposure_rank,
    -- Il centroide, per portare la mappa sul comune quando si clicca la
    -- riga. Viene da qui e non da una seconda richiesta: la vista ce l'ha
    -- già calcolato, e le tre righe per pericolo hanno lo stesso comune.
    ST_X((array_agg(centroid))[1])         AS lon,
    ST_Y((array_agg(centroid))[1])         AS lat,
    -- Solo fra i pericoli misurati: ordinare sulla priorità di uno zero per
    -- assenza di dato metterebbe in coda un comune di cui non sappiamo
    -- niente, che è il posto sbagliato.
    max(COALESCE(priority, 0)) FILTER (WHERE measured) AS max_priority
FROM mv_comune_risk
GROUP BY istat_code, name, aoi_id
"""


def _to_comune(row: Any) -> dict[str, Any]:
    hazards = row["hazards"]
    if isinstance(hazards, str):  # asyncpg restituisce jsonb come testo
        hazards = json.loads(hazards)
    # Il numero che porta il comune all'attenzione. Si compone qui e non in
    # SQL perché ha una soglia di classe, e le soglie stanno nella
    # configurazione: scriverla nella query vorrebbe dire due copie della
    # stessa regola, libere di divergere.
    attenzione = attention_index(
        {
            h: HazardStanding(
                priority=float(v.get("priority") or 0.0),
                level=RiskLevel(str(v["class"])),
                measured=bool(v.get("measured", True)),
            )
            for h, v in hazards.items()
        },
        rule=load_cascades().attention,
    )
    return {
        "istat_code": row["istat_code"],
        "name": row["name"],
        "aoi_id": row["aoi_id"],
        "worst_hazard": row["worst_hazard"],
        "worst_class": row["worst_class"],
        "max_score": round(float(row["max_score"] or 0.0), 3),
        "n_cells": int(row["n_cells"]),
        "n_alert": int(row["n_alert"]),
        "counts": {
            "None": int(row["n_none"]),
            "Low": int(row["n_low"]),
            "Moderate": int(row["n_moderate"]),
            "High": int(row["n_high"]),
            "VeryHigh": int(row["n_veryhigh"]),
        },
        "exposure_rank": round(float(row["exposure_rank"] or 0.0), 3),
        "lon": round(float(row["lon"]), 5),
        "lat": round(float(row["lat"]), 5),
        # `None` quando non c'è niente di misurato: chi lo mostra deve
        # scrivere «non misurato», non «0,00».
        "attention": None if attenzione is None else round(attenzione, 3),
        # I tre indicatori affiancati: la riga della dashboard li mostra tutti,
        # anche a zero, perché un trattino è una risposta e una colonna che
        # sparisce non lo è.
        "hazards": {
            h: {
                "class": str(v["class"]),
                "score": round(float(v["score"] or 0.0), 3),
                # C'era nel DTO e nella query, non nella risposta: usciva
                # sempre 0,000 pur essendo documentata come «la priorità che
                # il dispacciatore degli alert usa». Un campo che vale
                # sempre zero è peggio di un campo assente.
                "priority": round(float(v.get("priority") or 0.0), 3),
                "n_cells": int(v["n_cells"]),
                "n_alert": int(v["n_alert"]),
                "measured": bool(v.get("measured", True)),
            }
            for h, v in hazards.items()
        },
    }


#: La previsione per comune, dallo stato previsionale corrente (057).
#:
#: Qui sì il massimo su **tutte** le celle, non la cella peggiore di oggi: la
#: previsione serve proprio a vedere il versante che adesso è tranquillo e
#: domani no, e seguire la cella peggiore di oggi lo nasconderebbe. Si può
#: perché `latest_forecast` è una tabella piccola e non partizionata: la
#: stessa domanda sullo storico costava 755 ms per comune.
_PREVISIONE_PER_COMUNE = """
SELECT cc.istat_code,
       lf.hazard_type::text                              AS hazard,
       lf.horizon_h,
       max(lf.score)                                     AS score,
       (array_agg(lf.class ORDER BY lf.score DESC))[1]   AS class,
       max(lf.target_at)                                 AS target_at,
       max(lf.score * (1.0 + COALESCE(f.exposure_norm, 0.0))) AS priority
FROM cell_comune cc
JOIN latest_forecast lf ON lf.cell_id = cc.cell_id
LEFT JOIN cell_static_factors f ON f.cell_id = cc.cell_id
WHERE cc.istat_code = ANY($1::text[])
GROUP BY 1, 2, 3
"""

#: Per ordinare la classifica sul futuro invece che sull'adesso.
_PRIORITA_PREVISTA = """
SELECT cc.istat_code,
       max(lf.score * (1.0 + COALESCE(f.exposure_norm, 0.0))) AS fc_priority
FROM latest_forecast lf
JOIN cell_comune cc ON cc.cell_id = lf.cell_id
LEFT JOIN cell_static_factors f ON f.cell_id = lf.cell_id
GROUP BY 1
"""


async def _previsioni(conn: Any, istat_codes: list[str]) -> dict[str, dict[str, Any]]:
    """Per ogni comune e pericolo, il picco previsto e quando arriva.

    Il picco su tutti gli orizzonti: la domanda è «quanto andrà male, e
    quando», e rispondere con tre numeri per pericolo — +24, +48, +72 —
    rimanderebbe la sintesi a chi legge.
    """
    if not istat_codes:
        return {}
    rows = await conn.fetch(_PREVISIONE_PER_COMUNE, istat_codes)
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        per_pericolo = out.setdefault(str(r["istat_code"]), {})
        hazard = str(r["hazard"])
        corrente = per_pericolo.get(hazard)
        if corrente is None or float(r["score"]) > corrente["score"]:
            per_pericolo[hazard] = {
                "score": round(float(r["score"]), 3),
                "class": str(r["class"]),
                "horizon_h": int(r["horizon_h"]),
                "target_at": r["target_at"].isoformat(),
                "priority": round(float(r["priority"]), 3),
            }
    return out


def _con_previsione(comune: dict[str, Any], previsto: dict[str, Any]) -> dict[str, Any]:
    """Aggiunge alla riga il futuro, e il numero di attenzione previsto.

    L'attenzione prevista si compone con la stessa regola di quella di
    adesso — massimo più incremento per i pericoli concomitanti — così i due
    numeri sono confrontabili: se il secondo è più alto, il comune sta
    salendo.

    Un pericolo senza riga previsionale **non è ignoto**: lo stato
    previsionale tiene solo le celle da Moderato in su, e l'assenza vuol dire
    previsto sotto soglia. Per questo entra nel conto come «sotto soglia» e
    non viene escluso come i non misurati.
    """
    attenzione = attention_index(
        {
            h: HazardStanding(priority=float(v["priority"]), level=RiskLevel(str(v["class"])))
            for h, v in previsto.items()
        },
        rule=load_cascades().attention,
    )
    return {
        **comune,
        "forecast": previsto,
        "forecast_attention": None if attenzione is None else round(attenzione, 3),
    }


async def top_comuni(
    *,
    aoi_id: str | None,
    limit: int,
    min_rank: int = 2,
    query: str | None = None,
    order: str = "now",
) -> list[dict[str, Any]]:
    """I comuni ordinati dal numero di attenzione, su tutti i pericoli.

    `min_rank` è la soglia sotto cui un comune non entra in classifica: 2 è
    «Moderato», che è dove il sistema comincia a dire qualcosa. Con `query`
    la soglia non si applica — chi cerca il proprio comune per nome vuole
    vederlo comunque, anche quando non ha niente da segnalare, e quello è il
    caso in cui la risposta «nessun pericolo sopra soglia» è la notizia.

    L'ordinamento avviene in due tempi, e non è pigrizia. In SQL si ordina
    per la priorità massima, che è il termine dominante; in Python si applica
    l'incremento multi-pericolo e si riordina. Fare tutto in SQL vorrebbe
    dire riscrivere lì la regola — con la sua soglia di classe — e averne due
    copie; fare tutto in Python vorrebbe dire caricare tutti i settemila
    comuni a ogni richiesta. Si prende un margine di tre volte il limite, che
    è abbastanza perché l'incremento (al più +15% per pericolo in più) non
    possa far entrare in pagina un comune escluso dal taglio.
    """
    limit = max(1, min(limit, 200))
    margine = limit * 3
    async with acquire() as conn:
        if order == "forecast":
            # Sul futuro: la soglia di adesso non si applica, perché il punto
            # è proprio trovare il comune che oggi è sotto e domani no.
            rows = await conn.fetch(
                f"""
                WITH per_comune AS ({_PER_COMUNE}), previsti AS ({_PRIORITA_PREVISTA})
                SELECT pc.* FROM per_comune pc
                JOIN previsti pv ON pv.istat_code = pc.istat_code
                WHERE ($1::text IS NULL OR pc.aoi_id = $1)
                  AND ($3::text IS NULL OR pc.name ILIKE '%' || $3 || '%')
                ORDER BY pv.fc_priority DESC, pc.name
                LIMIT $2
                """,
                aoi_id,
                margine,
                query,
            )
        else:
            rows = await conn.fetch(
                f"""
                WITH per_comune AS ({_PER_COMUNE})
                SELECT * FROM per_comune
                WHERE ($1::text IS NULL OR aoi_id = $1)
                  AND ($3::text IS NULL OR name ILIKE '%' || $3 || '%')
                  AND ($4::text IS NOT NULL OR worst_rank >= $5)
                ORDER BY max_priority DESC NULLS LAST, worst_rank DESC, n_alert DESC, name
                LIMIT $2
                """,
                aoi_id,
                margine,
                query,
                query,
                min_rank,
            )
        previsioni = await _previsioni(conn, [str(r["istat_code"]) for r in rows])
    comuni = [
        _con_previsione(_to_comune(r), previsioni.get(str(r["istat_code"]), {})) for r in rows
    ]
    chiave = "forecast_attention" if order == "forecast" else "attention"
    # I comuni senza un numero vanno in coda: non sono tranquilli, ma nemmeno
    # ordinabili, e metterli in cima sarebbe un allarme inventato.
    comuni.sort(key=lambda c: (c[chiave] is None, -(c[chiave] or 0.0), c["name"]))
    return comuni[:limit]


async def comune_detail(istat_code: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            f"WITH per_comune AS ({_PER_COMUNE}) SELECT * FROM per_comune WHERE istat_code = $1",
            istat_code,
        )
        if row is None:
            return None
        cells = await conn.fetch(
            """
            SELECT m.cell_id, m.hazard_type::text AS hazard, m.score, m.class AS level,
                   m.computed_at,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat
            FROM cell_comune cc
            JOIN latest_risk m ON m.cell_id = cc.cell_id
            JOIN grid_cells g ON g.id = cc.cell_id
            WHERE cc.istat_code = $1 AND m.score IS NOT NULL
            ORDER BY m.score DESC NULLS LAST, m.cell_id
            LIMIT 200
            """,
            istat_code,
        )
        previsioni = await _previsioni(conn, [istat_code])
    out = _con_previsione(_to_comune(row), previsioni.get(istat_code, {}))
    return {
        "comune": out,
        "cells": [
            {
                "cell_id": str(c["cell_id"]),
                "hazard": str(c["hazard"]),
                "score": round(float(c["score"]), 3),
                "level": str(c["level"]),
                # Quando è stato calcolato: un punteggio senza data non si sa
                # se è di adesso o di ieri, e su un rischio è la differenza
                # fra un'informazione e un numero.
                "computed_at": c["computed_at"].isoformat(),
                "lon": float(c["lon"]),
                "lat": float(c["lat"]),
            }
            for c in cells
        ],
    }


#: L'andamento del comune: la storia della **cella peggiore di oggi**, per
#: pericolo.
#:
#: Non il massimo ricalcolato ora per ora su tutte le celle. Quella è la
#: domanda più fedele, ed è la prima che ho scritto: su Bardonecchia (134
#: celle, sette giorni, ventitré partizioni) ci mette **212 secondi**, e non
#: a freddo — rieseguita a cache calda non migliora, perché tocca davvero
#: troppi dati. Questa ne legge tre celle: 18 s la prima volta su questo
#: disco, **41 ms** dopo.
#:
#: Il cambio ha un prezzo e va detto: la cella peggiore di oggi poteva non
#: esserlo cinque giorni fa, quindi la linea è la storia di *quel* punto, non
#: l'inviluppo del comune. In compenso concorda con il numero in testata, che
#: è anch'esso la cella peggiore: un grafico che raccontasse un altro
#: aggregato accanto a quel numero sarebbe peggio che uno più stretto.
_CELLE_PEGGIORI = """
    SELECT DISTINCT ON (lr.hazard_type) lr.cell_id, lr.hazard_type
    FROM cell_comune cc
    JOIN latest_risk lr ON lr.cell_id = cc.cell_id
    WHERE cc.istat_code = $1
      -- Un pericolo non misurato non ha una cella peggiore da seguire
      -- (#143): meglio una linea in meno che una linea a zero.
      AND COALESCE(lr.measured, true)
    ORDER BY lr.hazard_type, lr.score DESC NULLS LAST
"""

_STORIA_COMUNE = f"""
WITH peggiori AS ({_CELLE_PEGGIORI})
SELECT date_trunc('hour', ra.computed_at) AS t,
       p.hazard_type::text                AS hazard,
       max(ra.score)                      AS score
FROM peggiori p
JOIN risk_assessments ra
      ON ra.cell_id = p.cell_id
     AND ra.hazard_type = p.hazard_type
WHERE ra.horizon NOT LIKE '+%'
  AND ra.computed_at >= now() - make_interval(hours => $2::int)
  AND ra.score IS NOT NULL
  AND COALESCE(ra.measured, true)
GROUP BY 1, 2
ORDER BY 1
"""

#: Il futuro del comune: per ogni orizzonte, la cella peggiore **prevista**,
#: dallo stato previsionale corrente (057).
#:
#: Non la cella peggiore di oggi, come per il passato: la previsione serve a
#: vedere il versante che adesso è tranquillo e domani no, e seguire quella
#: di oggi lo nasconderebbe. Il passato non può fare lo stesso perché lo
#: storico è partizionato — 212 s — mentre questa tabella è piccola e ha una
#: riga per cella.
_PREVISIONE_COMUNE = """
SELECT lf.hazard_type::text                            AS hazard,
       lf.horizon_h,
       max(lf.target_at)                               AS target_at,
       max(lf.score)                                   AS score,
       (array_agg(lf.class ORDER BY lf.score DESC))[1] AS class
FROM cell_comune cc
JOIN latest_forecast lf ON lf.cell_id = cc.cell_id
WHERE cc.istat_code = $1
GROUP BY 1, 2
ORDER BY 1, 2
"""


async def comune_history(
    istat_code: str, *, hours: int
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Il passato e il futuro del comune, una serie per pericolo.

    Il passato è **sparso** e resta tale: dalla #135 una cella lascia una riga
    solo quando cambia classe, si scosta oltre soglia, o scade il battito di
    24 ore. Sulle ore senza scrittura non c'è un punto, ed è corretto — chi
    disegna unisce i punti che esistono invece di inventare un livello per
    ogni ora.

    Il futuro è la cella peggiore prevista per ogni orizzonte, con il momento
    a cui si riferisce già composto. Un orizzonte assente vuol dire previsto
    sotto Moderato: lo stato previsionale tiene solo le celle sopra soglia.
    """
    async with acquire() as conn:
        osservate = await conn.fetch(_STORIA_COMUNE, istat_code, hours)
        previste = await conn.fetch(_PREVISIONE_COMUNE, istat_code)

    passato: dict[str, list[dict[str, Any]]] = {}
    for r in osservate:
        passato.setdefault(str(r["hazard"]), []).append(
            {"t": r["t"].isoformat(), "score": round(float(r["score"]), 3)}
        )

    futuro: dict[str, list[dict[str, Any]]] = {}
    for r in previste:
        futuro.setdefault(str(r["hazard"]), []).append(
            {
                "t": r["target_at"].isoformat(),
                "score": round(float(r["score"]), 3),
                "level": str(r["class"]),
            }
        )
    for punti in futuro.values():
        punti.sort(key=lambda p: str(p["t"]))

    return {"observed": passato, "forecast": futuro}
