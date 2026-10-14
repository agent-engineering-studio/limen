"""La pipeline notturna: i passi in ordine, una volta per notte (#78).

Prima erano schedule indipendenti — drift ogni N ore, forecast history ogni 6,
cache cleanup ogni 5 minuti, shadow dentro ogni sweep orario — che si
incrociavano senza sapere l'uno dell'altro. Il caso peggiore era il
riaddestramento: il monitor del drift poteva chiedere un retrain mentre lo
sweep orario stava girando, sulla stessa macchina, contendendosi la CPU con la
cosa che deve stare dentro il tick.

L'ordine qui non è estetico, è una dipendenza: lo shadow scrive in
``model_runs``, il drift confronta ``model_runs`` con i campioni di training, e
il retrain parte solo se il drift l'ha chiesto. Gli ultimi tre passi non
dipendono da nessuno e chiudono la notte con la manutenzione.

**Un passo che fallisce non ferma i successivi.** Ogni passo ha la sua riga in
`job_runs` con `scope=<passo>`: un drift che esplode non deve impedire alle
partizioni di domani di esistere, e la riga dice quale dei sei è andato male
senza dover leggere i log.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from limen.api.dependencies import AppDependencies
from limen.api.jobs._tracking import tracked
from limen.api.jobs.cache_cleanup import run_cache_cleanup_job
from limen.api.jobs.drift_monitor import run_drift_monitor_job
from limen.api.jobs.ids import JOB_NIGHTLY
from limen.api.jobs.partitions import run_partitions_job
from limen.config.settings import SchedulerBackend, ScoringMode
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import HazardType
from limen.data.db import acquire

log = get_logger(__name__)

#: I passi, nell'ordine in cui girano. Elencati qui e non solo nel codice
#: perché è la lista che i test e `limen jobs` si aspettano di trovare. La
#: previsione per cella non c'è più: gira quattro volte al giorno con il suo
#: schedule (`JOB_FORECAST_HISTORY`).
STEPS = (
    "fwi_pioggia_osservata",
    "shadow_ml",
    "drift_monitor",
    "retrain",
    "partitions_maintain",
    "retention",
    "storage",
    "egms_release",
    "radar_archivio",
    "glofas_riferimenti",
)


async def _step(name: str, fn: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any] | None:
    """Esegui un passo tracciato. ``None`` se è fallito — il chiamante prosegue."""
    async with tracked(JOB_NIGHTLY, scope=name) as metrics:
        try:
            out = await fn()
        except Exception as exc:
            log.error(
                "job.nightly.step_failed",
                step=name,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            metrics["status"] = "error"
            metrics["error_type"] = type(exc).__name__
            return None
        metrics.update(out)
        return out


async def _all_aois() -> list[str]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT id FROM aoi ORDER BY id")
    return [str(r["id"]) for r in rows]


async def _shadow_one_aoi(
    *,
    workflow: Any,
    hazard: HazardType,
    aoi_id: str,
    enable_insitu: bool,
    limit: asyncio.Semaphore,
) -> int:
    """Una regione sotto semaforo. Funzione di modulo per la stessa ragione
    dello sweep orario: una chiusura dentro il ciclo catturerebbe `hazard` e
    `workflow` per riferimento (ruff B023)."""
    async with limit:
        ctx = MonitoringContext(
            aoi_id=aoi_id,
            hazard_type=hazard,
            valuation_time=datetime.now(UTC),
            enable_insitu=enable_insitu,
        )
        result = await workflow.run(ctx)
        return len(result.context.cell_results)


async def _shadow_ml(deps: AppDependencies) -> dict[str, Any]:
    """Champion + challenger su tutte le regioni, senza persistere né allertare.

    Il profilo ``nightly`` toglie `PersistResult` e `AlertDispatch`: il notturno
    misura il challenger, non governa la mappa. Quello che resta è la scrittura
    in ``model_runs`` che lo `ShadowChallengerExecutor` fa di suo, ed è l'unica
    cosa che il drift del passo dopo legge.
    """
    settings = deps.settings
    if settings.scoring.mode is not ScoringMode.SHADOW:
        return {"status": "skipped", "reason": "scoring mode is not shadow"}
    aois = await _all_aois()
    if not aois:
        return {"status": "skipped", "reason": "no aoi"}

    scored: dict[str, int] = {}
    for hazard in settings.hazards.enabled:
        try:
            workflow = deps.build_workflow(hazard=hazard, profile="nightly")
        except Exception as exc:
            log.error(
                "job.nightly.shadow.workflow_unavailable",
                hazard=hazard.value,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue
        limit = asyncio.Semaphore(settings.scheduler.sweep_concurrency)
        results = await asyncio.gather(
            *(
                _shadow_one_aoi(
                    workflow=workflow,
                    hazard=hazard,
                    aoi_id=aoi_id,
                    enable_insitu=settings.enable_insitu,
                    limit=limit,
                )
                for aoi_id in aois
            ),
            return_exceptions=True,
        )
        for aoi_id, item in zip(aois, results, strict=True):
            if isinstance(item, BaseException):
                log.error("job.nightly.shadow.aoi_failed", aoi_id=aoi_id, error=str(item))
                continue
            scored[aoi_id] = scored.get(aoi_id, 0) + item
    return {"aois": len(scored), "cells": sum(scored.values())}


async def _retrain(deps: AppDependencies, *, triggered: bool) -> dict[str, Any]:
    """`uv run limen train` in un sottoprocesso, se il drift l'ha chiesto.

    Sottoprocesso e non chiamata diretta: Optuna gira decine di trial con i
    suoi thread e la sua memoria, e farlo dentro il worker significherebbe che
    lo sweep del mattino eredita un processo gonfio. Un processo che finisce
    restituisce la memoria per costruzione.

    Il cancello di promozione resta un **tag** (invariante): questo passo
    addestra e registra, non promuove niente.
    """
    if not triggered:
        return {"status": "skipped", "reason": "no drift trigger"}
    if not deps.settings.training.auto_retrain:
        return {"status": "skipped", "reason": "TRAINING__AUTO_RETRAIN is false"}
    # Il tetto è il budget di Optuna più mezz'ora: oltre, non è lento — è
    # bloccato, e una notte intera appesa a un training non finisce mai.
    timeout = deps.settings.training.optuna_timeout_seconds + 1800
    proc = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        "limen",
        "train",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return {"status": "error", "reason": f"timed out after {timeout}s"}
    if proc.returncode != 0:
        return {
            "status": "error",
            "returncode": proc.returncode,
            "stderr": stderr.decode(errors="replace")[-2000:],
        }
    return {"returncode": 0}


async def run_nightly_pipeline(deps: AppDependencies) -> dict[str, Any]:
    """I passi notturni, in ordine. Ritorna il riepilogo per passo."""
    out: dict[str, Any] = {}

    # Per primo: la previsione per cella delle 02:20 riparte dallo stato FWI
    # salvato, e deve trovarlo già bagnato dalla pioggia di ieri.
    out["fwi_pioggia_osservata"] = await _step("fwi_pioggia_osservata", _fwi_pioggia_osservata)
    out["shadow_ml"] = await _step("shadow_ml", lambda: _shadow_ml(deps))

    drift = await _step("drift_monitor", lambda: _drift(deps))
    out["drift_monitor"] = drift

    out["retrain"] = await _step(
        "retrain",
        lambda: _retrain(deps, triggered=bool((drift or {}).get("triggered"))),
    )
    out["partitions_maintain"] = await _step("partitions_maintain", lambda: _partitions(deps))
    out["retention"] = await _step("retention", lambda: _retention(deps))
    out["storage"] = await _step("storage", lambda: _storage(deps))
    out["egms_release"] = await _step("egms_release", lambda: _egms_release(deps))
    out["radar_archivio"] = await _step("radar_archivio", lambda: _radar_archivio(deps))
    # Per ultimo: il tetto di GloFAS riparte a mezzanotte UTC, quindi alle due
    # è intero comunque, e il riempimento ora dura un paio d'ore (i lotti si
    # distanziano sotto il limite orario): davanti, terrebbe ferma la retention.
    out["glofas_riferimenti"] = await _step("glofas_riferimenti", lambda: _glofas(deps))

    log.info("job.nightly.done", steps={k: v is not None for k, v in out.items()})
    return out


async def _drift(deps: AppDependencies) -> dict[str, Any]:
    return {"triggered": bool(await run_drift_monitor_job(deps))}


async def _glofas(deps: AppDependencies) -> dict[str, Any]:
    """La portata ordinaria dei nodi GloFAS che ancora non ce l'hanno (#200)."""
    from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
    from limen.integrations.openmeteo.glofas_riferimenti import riempi

    flood = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(flood, FloodThresholds)
    return await riempi(
        chiamate=deps.settings.scheduler.glofas_chiamate_per_notte,
        soglia_pioggia_mm=flood.pluvial.threshold_mm,
        percentile=flood.fluvial.reference_percentile,
        window_days=flood.fluvial.reference_window_days,
    )


async def _egms_release(deps: AppDependencies) -> dict[str, Any]:
    """Una richiesta: è uscita una release EGMS più nuova di `EGMS__RELEASE`?"""
    from limen.integrations.egms.sync_job import controlla_release

    return dict(await controlla_release(deps.settings))


async def _fwi_pioggia_osservata() -> dict[str, Any]:
    """Gli ultimi giorni della catena FWI rifatti con la pioggia del DPC e il
    meteo analizzato al posto della previsione con cui erano stati scritti."""
    from datetime import timedelta

    from limen.cli.fwi_backfill import params_from
    from limen.core.scoring.regional_thresholds import (
        WildfireThresholds,
        load_hazard_thresholds,
    )
    from limen.integrations.dpc.fwi_pioggia import correggi, fonte_dpc, meteo_open_meteo

    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    cfg = t.fwi.observed_rain
    if cfg is None:
        return {"status": "skipped", "reason": "wildfire.yaml senza fwi.observed_rain"}
    oggi = datetime.now(UTC).date()
    return dict(
        await correggi(
            dal=oggi - timedelta(days=cfg.days),
            al=oggi,
            params=params_from(t),
            max_gap_days=t.fwi.max_gap_days,
            fonte=fonte_dpc(cfg.max_step_mm),
            meteo=meteo_open_meteo(),
        )
    )


async def _radar_archivio(deps: AppDependencies) -> dict[str, Any]:
    """Il radar DPC «Merging» della notte prima, prima che il DPC lo perda."""
    from pathlib import Path

    from limen.integrations.dpc.merging_archive import archivia

    cfg = deps.settings.radar_archive
    if not cfg.attivo:
        return {"status": "skipped", "reason": "RADAR_ARCHIVE__CARTELLA non impostata"}
    return dict(await archivia(Path(cfg.cartella), giorni=cfg.giorni, massimo=cfg.file_per_notte))


async def _partitions(deps: AppDependencies) -> dict[str, Any]:
    return {"dropped": await run_partitions_job(deps)}


async def _storage(deps: AppDependencies) -> dict[str, Any]:
    """Quanto pesa il database, e un avviso prima che il volume finisca.

    Il 2026-09-28 `/srv/pgfast` è arrivato al 100% e Postgres è andato in
    crash loop: nessuno se n'era accorto prima, perché niente guardava. Un
    sistema che monitora il territorio e non si accorge del proprio disco
    pieno ha un problema suo.

    Lo spazio libero del filesystem da SQL non si vede — il database gira in
    un altro container e Postgres non espone una `statvfs`. Si guarda quindi
    ciò che si può misurare da qui: quanto pesa, e quali tabelle pesano. La
    dimensione finisce fra le metriche di `job_runs`, così la *crescita*
    diventa leggibile nello storico dei run anche senza soglia.
    """
    async with acquire() as conn:
        size = int(await conn.fetchval("SELECT pg_database_size(current_database())"))
        rows = await conn.fetch(
            """
            SELECT c.relname, pg_total_relation_size(c.oid) AS bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'm')
            ORDER BY 2 DESC
            LIMIT 3
            """
        )
    gb = size / 1024**3
    soglia = deps.settings.scoring.db_size_warn_gb
    out: dict[str, Any] = {
        "db_size_gb": round(gb, 1),
        "warn_at_gb": soglia,
        "largest": {str(r["relname"]): round(int(r["bytes"]) / 1024**3, 1) for r in rows},
    }
    if soglia and gb >= soglia:
        # `warning` e non `error`: il database funziona, è il margine che sta
        # finendo. Chi legge i log deve poterlo distinguere da un guasto.
        log.warning("job.nightly.storage_near_limit", **out)
        out["status"] = "warn"
    return out


async def _retention(deps: AppDependencies) -> dict[str, Any]:
    """La purga della cache, una volta a notte invece che ogni cinque minuti.

    `PostgresCache` filtra già sulla scadenza in lettura (`expires_at > now()`),
    quindi una riga scaduta non è mai servita: cancellarla è manutenzione del
    disco, non correttezza, e trecento tick al giorno per quello erano
    trecento tick di troppo.

    Sotto il backend pg_cron la purga la fa il database, come prima:
    `SCHEDULER__CACHE_CLEANUP` continua a dire *chi* la fa, questo passo
    cambia solo *quando* la fa il worker.
    """
    if deps.settings.scheduler.cache_cleanup is not SchedulerBackend.APSCHEDULER:
        return {"status": "skipped", "reason": "cache cleanup runs under pg_cron"}
    return {"cache_rows": await run_cache_cleanup_job(deps)}
