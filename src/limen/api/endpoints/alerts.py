"""Recent alerts endpoint — high-or-above persisted assessments."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response

from limen.api.dependencies import DepsDep
from limen.api.schemas import AlertItem, AlertsResponse
from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.scoring.exposure import exposure_factor_from_row
from limen.core.scoring.regional_thresholds import ExposureBlock, load_hazard_thresholds
from limen.data.db import acquire

log = get_logger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=AlertsResponse)
async def list_alerts(
    response: Response,
    deps: DepsDep,  # noqa: ARG001 — DI presence
    threshold: str = Query("High", description="Minimum risk level to include"),
    since_hours: int = Query(72, ge=1, le=24 * 30),
    limit: int = Query(200, ge=1, le=2000),
    hazard: HazardType = DEFAULT_HAZARD,
) -> AlertsResponse:
    """Return the most recent persisted alerts above ``threshold``."""
    response.headers["Cache-Control"] = "public, max-age=30"
    valid = {"None", "Low", "Moderate", "High", "VeryHigh"}
    if threshold not in valid:
        threshold = "High"

    # Levels at or above the requested threshold. Order is fixed so we
    # can short-circuit on string equality in the WHERE clause.
    order = ["None", "Low", "Moderate", "High", "VeryHigh"]
    levels_to_include = order[order.index(threshold) :]

    # Lo stato corrente per cella viene da `latest_risk` (#125), non dallo
    # storico. Cercarlo in `risk_assessments` significava un DISTINCT ON su
    # tutte le righe della finestra: misurate **1.059.909 righe e 119
    # secondi** per il solo conteggio, con l'endpoint che rispondeva 500 per
    # timeout — è l'errore che la dashboard mostrava sul pannello «celle
    # sopra soglia».
    #
    # `since_hours` cambia significato, e in meglio: non è più «ha superato
    # la soglia in qualche momento delle ultime N ore» — una domanda che
    # nessuna etichetta della pagina prometteva — ma «il suo ultimo calcolo
    # non è più vecchio di N ore». È un filtro di freschezza: una cella la
    # cui regione non viene valutata da due giorni non deve comparire in un
    # elenco che il lettore legge come «adesso».
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT lr.cell_id, lr.score, lr.class, lr.computed_at
                FROM latest_risk lr
                WHERE lr.class = ANY($1::text[])
                  AND lr.hazard_type = $3
                  AND lr.computed_at >= now() - ($2::int * interval '1 hour')
            )
            -- Esposizione: 11x tessuto urbano CORINE (in cella + adiacenti
            -- ~2 km) e distanza precomputata dalla rete OSM principale
            -- (strade motorway..secondary, ferrovie). I flag CORINE 12x
            -- restano il fallback quando le distanze OSM sono NULL.
            -- Calcolata DOPO la dedup: solo sulle celle uniche, non su
            -- ogni tick orario.
            SELECT l.cell_id, g.aoi_id, l.score, l.class, l.computed_at,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat,
                   (csf.landuse_code LIKE '11%') AS urban_here,
                   (csf.landuse_code LIKE '12%') AS infra_here,
                   csf.near_urban AS urban_near,
                   csf.near_infra AS infra_near,
                   csf.distance_to_road_m,
                   csf.distance_to_rail_m,
                   csf.nearest_road_class,
                   csf.wui_proximity_norm
            FROM latest l
            JOIN grid_cells g ON g.id = l.cell_id
            LEFT JOIN cell_static_factors csf ON csf.cell_id = l.cell_id
            """,
            levels_to_include,
            since_hours,
            hazard.value,
        )

    if not rows:
        # Nessuna riga da ordinare, quindi nessuna soglia da caricare. Uscire
        # qui è ciò che rende un pericolo valido ma non abilitato una risposta
        # vuota invece di un 500: la sua configurazione non esiste ancora, e
        # chiederla per ordinare zero righe sarebbe lavoro inutile e fatale.
        return AlertsResponse(items=[])

    # Priorità = rischio x (1 + esposizione): la stessa formula del
    # dispatcher degli alert (limen.core.scoring.exposure, soglie nel file
    # del pericolo). Una frana Moderate sopra un paese o una statale conta
    # più di una identica su un versante disabitato.
    try:
        cfg: ExposureBlock | None = load_hazard_thresholds(hazard).exposure
    except FileNotFoundError:
        # Righe di un pericolo la cui configurazione non è ancora nel pacchetto.
        # L'elenco resta corretto, ordinato per solo punteggio: degradare a
        # neutro è ciò che l'invariante chiede a una lettura senza sorgente,
        # e sopprimere l'elenco sarebbe peggio che ordinarlo meno bene.
        log.warning("integration.degraded", surface="alerts.exposure", hazard=hazard.value)
        cfg = None
    scored = []
    for r in rows:
        factor, tags = exposure_factor_from_row(r, cfg) if cfg is not None else (0.0, None)
        scored.append((float(r["score"]) * (1.0 + factor), tags, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    scored = scored[:limit]

    from limen.integrations.geoserver_source.comuni import comuni_for_points

    places = await comuni_for_points([(float(r["lon"]), float(r["lat"])) for _, _, r in scored])

    items = [
        AlertItem(
            cell_id=str(r["cell_id"]),
            aoi_id=str(r["aoi_id"]),
            hazard_type=hazard,
            score=float(r["score"]),
            level=str(r["class"]),
            computed_at=r["computed_at"],
            lon=float(r["lon"]),
            lat=float(r["lat"]),
            place=place,
            exposure=", ".join(tags) if tags else None,
            priority=round(priority, 3),
        )
        for (priority, tags, r), place in zip(scored, places, strict=True)
    ]
    return AlertsResponse(items=items)


@router.get("/forecast/schedule")
async def forecast_schedule(deps: DepsDep, response: Response) -> dict[str, object]:
    """Quando gira il prossimo calcolo previsionale, e com'è andato l'ultimo."""
    from limen.api.jobs.ids import JOB_FORECAST_HISTORY, JOB_FORECAST_MONITORING
    from limen.data.repos.forecast_schedule import forecast_schedule as leggi

    response.headers["Cache-Control"] = "public, max-age=30"
    return await leggi(
        JOB_FORECAST_MONITORING,
        cells_job_id=JOB_FORECAST_HISTORY,
        interval_hours=deps.settings.forecast.interval_hours,
        horizon_hours=deps.settings.forecast.horizon_hours,
    )


@router.get("/forecast")
async def list_forecast_alerts(
    deps: DepsDep,  # noqa: ARG001 — DI presence
    since_hours: int = Query(72, ge=1, le=24 * 30),
    limit: int = Query(50, ge=1, le=500),
    hazard: HazardType | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Predictive (PREVISIONE) dispatches from the forecast sweep.

    Senza ``hazard``, tutti i pericoli. Il default era le frane, e il pannello
    della previsione diceva «nessuna regione prevista sopra soglia» la mattina
    in cui erano partiti avvisi d'incendio per cinque regioni.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT aoi_id, hazard_type, horizon_h, max_level, max_score,
                   cells_alerted, summary, dispatched_at
            FROM forecast_dispatches
            WHERE dispatched_at >= now() - make_interval(hours => $1)
              AND ($3::hazard_type IS NULL OR hazard_type = $3::hazard_type)
            ORDER BY dispatched_at DESC
            LIMIT $2
            """,
            since_hours,
            limit,
            hazard.value if hazard else None,
        )
    return {
        "items": [
            {
                "aoi_id": str(r["aoi_id"]),
                "hazard_type": str(r["hazard_type"]),
                "horizon_h": int(r["horizon_h"]),
                "max_level": str(r["max_level"]),
                "max_score": float(r["max_score"]),
                "cells_alerted": int(r["cells_alerted"]),
                "summary": r["summary"],
                "dispatched_at": r["dispatched_at"].isoformat(),
            }
            for r in rows
        ]
    }
