"""I fatti del riepilogo sulla qualità dei dati (#421), in sola lettura."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from limen.core.qualita_dati import Cadenza, Errore, Fatti, pulisci
from limen.data.db import acquire

#: Il passo notturno che scrive i fatti: la settimana dopo li rilegge da qui.
JOB = "limen-nightly"
SCOPE = "qualita_dati"


async def raccogli(adesso: datetime) -> Fatti:
    async with acquire() as conn:
        errori = await conn.fetch(
            """
            SELECT job_id, scope, count(*) AS volte, max(started_at) AS ultimo,
                   (array_agg(error ORDER BY started_at DESC))[1] AS messaggio
              FROM job_runs
             WHERE status = 'error' AND started_at > $1::timestamptz - interval '24 hours'
             GROUP BY job_id, scope
            """,
            adesso,
        )
        cadenze = await conn.fetch(
            """
            WITH ok AS (
                SELECT job_id, scope, finished_at,
                       lag(finished_at) OVER (
                           PARTITION BY job_id, scope ORDER BY finished_at
                       ) AS prima
                  FROM job_runs
                 WHERE status = 'ok' AND finished_at IS NOT NULL
                   AND finished_at > $1::timestamptz - interval '30 days'
            )
            SELECT job_id, scope, max(finished_at) AS ultimo,
                   percentile_cont(0.5) WITHIN GROUP (
                       ORDER BY extract(epoch FROM finished_at - prima)
                   ) AS mediana_s,
                   count(prima) AS intervalli
              FROM ok
             GROUP BY job_id, scope
            """,
            adesso,
        )
        misurate = await conn.fetch(
            """
            SELECT hazard_type,
                   count(*) FILTER (WHERE measured = false) AS non_misurate,
                   count(*) AS totale
              FROM latest_risk
             GROUP BY hazard_type
            """
        )
    return Fatti(
        adesso=adesso,
        errori=[
            Errore(
                job_id=r["job_id"],
                scope=r["scope"],
                volte=int(r["volte"]),
                ultimo=r["ultimo"],
                messaggio=pulisci(r["messaggio"]) if r["messaggio"] else None,
            )
            for r in errori
        ],
        cadenze=[
            Cadenza(
                job_id=r["job_id"],
                scope=r["scope"],
                ultimo_successo=r["ultimo"],
                mediana=timedelta(seconds=float(r["mediana_s"] or 0.0)),
                intervalli=int(r["intervalli"]),
            )
            for r in cadenze
        ],
        non_misurate={
            str(r["hazard_type"]): (int(r["non_misurate"]), int(r["totale"])) for r in misurate
        },
    )


async def settimana_prima(adesso: datetime) -> dict[str, Any] | None:
    """Le metriche del passo di sette giorni fa (± mezza giornata), se c'è."""
    async with acquire() as conn:
        metrics = await conn.fetchval(
            """
            SELECT metrics FROM job_runs
             WHERE job_id = $1 AND scope = $2 AND status = 'ok'
               AND started_at BETWEEN $3::timestamptz - interval '12 hours'
                                  AND $3::timestamptz + interval '12 hours'
             ORDER BY started_at DESC LIMIT 1
            """,
            JOB,
            SCOPE,
            adesso - timedelta(days=7),
        )
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    return dict(metrics) if isinstance(metrics, dict) else None


__all__ = ["JOB", "SCOPE", "raccogli", "settimana_prima"]
