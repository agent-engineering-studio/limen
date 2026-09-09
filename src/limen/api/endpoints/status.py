"""Stato dei job: "aggiornato alle", per regione (#75).

Pubblico e in sola lettura come il resto della mappa. Nessuna logica: legge
il repo e lo serializza.

Perché un endpoint e non solo la CLI: chi guarda la mappa deve poter sapere
**quanto è vecchio** ciò che vede. Un punteggio di rischio senza la sua ora è
un numero di cui non si conosce la validità, e su una dashboard pubblica di
protezione civile è la differenza fra un'informazione e un'illusione.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from limen.api.jobs.ids import JOB_HOURLY_MONITORING
from limen.api.schemas import JobRunStatus, JobStatusResponse, SweepStatus
from limen.data.repos import job_runs_repo

router = APIRouter(prefix="/api/status", tags=["status"])

#: Un minuto. Lo sweep dura molto più di così, quindi una cache più corta
#: servirebbe solo a moltiplicare le richieste senza mostrare niente di nuovo.
_CACHE_SECONDS = 60


@router.get("/jobs", response_model=JobStatusResponse)
async def job_status(response: Response) -> JobStatusResponse:
    """Ultimo sweep nazionale e ultimo aggiornamento per regione."""
    response.headers["Cache-Control"] = f"public, max-age={_CACHE_SECONDS}"
    per_aoi = await job_runs_repo.latest_per_scope(JOB_HOURLY_MONITORING)
    national = await job_runs_repo.latest_global(JOB_HOURLY_MONITORING)
    return JobStatusResponse(
        sweep=(
            None
            if national is None
            else SweepStatus(
                started_at=national.started_at,
                finished_at=national.finished_at,
                status=national.status,
                duration_s=national.duration_s,
            )
        ),
        per_aoi=[
            JobRunStatus(
                aoi_id=run.scope or "",
                last_assessed_at=run.finished_at,
                duration_s=run.duration_s,
                status=run.status,
                cells=(
                    int(run.metrics["cells"])
                    if isinstance(run.metrics.get("cells"), (int, float))
                    else None
                ),
            )
            for run in per_aoi
            if run.scope
        ],
    )


__all__ = ["router"]
