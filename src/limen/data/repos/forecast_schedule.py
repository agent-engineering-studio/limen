"""Quando gira il prossimo calcolo previsionale, e com'è andato l'ultimo.

La previsione è il cuore dell'applicazione e chi la legge deve sapere quanto
è fresca: una previsione a +48 ore calcolata sei ore fa guarda già a +42.
Qui si compongono le tre cose che servono a dirlo — il prossimo scatto, che
lo scheduler pubblica dal worker; l'ultima corsa, da `job_runs`; e se ce n'è
una in corso adesso.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from limen.data.caching.postgres_cache import PostgresCache
from limen.data.db import acquire
from limen.data.repos import job_runs_repo

#: La chiave che il worker scrive a ogni battito (`limen.cli.worker`).
NEXT_FIRE_KEY = "scheduler:next_fire"


async def forecast_schedule(
    job_id: str,
    *,
    interval_hours: int,
    horizon_hours: int,
    cells_job_id: str,
) -> dict[str, Any]:
    """Lo stato del calcolo previsionale, pronto da mostrare.

    Sono **due** calcoli, e vanno detti tutti e due. L'allerta previsionale
    per regione gira ogni `interval_hours`; la previsione **per cella** —
    quella che finisce nel grafico dei comuni — gira dentro il job notturno
    (`cells_job_id`), una volta al giorno. Mostrare solo il primo timer
    lascerebbe credere che la curva di un comune si aggiorni ogni sei ore.

    `next_run_at` è ``None`` quando il worker non l'ha pubblicato: worker
    fermo, appena ripartito, o scheduler previsionale spento. È «non lo so»,
    e chi lo mostra deve dirlo invece di indovinare dall'ultima corsa —
    dopo un riavvio quella stima sbaglia di ore.
    """
    try:
        prossimi = await PostgresCache().get_json(NEXT_FIRE_KEY) or {}
    except Exception:
        prossimi = {}
    prossimo = prossimi.get(job_id) if isinstance(prossimi, dict) else None

    corse = await job_runs_repo.recent(job_id, limit=5)
    in_corso = next((r for r in corse if r.status == "running" and r.finished_at is None), None)
    conclusa = next((r for r in corse if r.finished_at is not None), None)

    # L'età vera della previsione per cella: quando è stata scritta l'ultima
    # riga, per pericolo. È ciò che chi guarda il grafico deve sapere — una
    # previsione a +48 ore fatta ieri notte guarda ormai a +30.
    try:
        async with acquire() as conn:
            corse_celle = await conn.fetch(
                "SELECT hazard_type::text AS hazard, max(run_at) AS run_at "
                "FROM latest_forecast GROUP BY 1"
            )
    except Exception:
        corse_celle = []

    return {
        "cells": {
            "next_run_at": prossimi.get(cells_job_id) if isinstance(prossimi, dict) else None,
            "last_run_by_hazard": {str(r["hazard"]): r["run_at"].isoformat() for r in corse_celle},
        },
        "interval_hours": interval_hours,
        "horizon_hours": horizon_hours,
        "next_run_at": prossimo,
        # Una riga `running` più vecchia di due intervalli è una corsa morta
        # con il worker, non un calcolo in corso: il riavvio la lascia aperta.
        "running_since": (
            in_corso.started_at.isoformat()
            if in_corso is not None
            and (datetime.now(in_corso.started_at.tzinfo) - in_corso.started_at).total_seconds()
            < interval_hours * 2 * 3600
            else None
        ),
        "last_run": (
            None
            if conclusa is None
            else {
                "started_at": conclusa.started_at.isoformat(),
                "finished_at": conclusa.finished_at.isoformat() if conclusa.finished_at else None,
                "status": conclusa.status,
                "duration_s": conclusa.duration_s,
            }
        ),
    }
