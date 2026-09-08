"""Svuota la coda degli alert in un messaggio riepilogativo (issue #59).

Quando il rate limit trattiene un ciclo, gli aggregati comunali restano in
``alert_aggregates`` con stato ``queued``. Questo job li ritira e ne fa **un**
messaggio, raggruppato per comune.

È anche il punto in cui l'**alert congiunto** della #58 diventa reale, e non
per caso: il workflow è per pericolo — un'esecuzione separata per ogni coppia
(pericolo, AOI), ognuna con i suoi alert — quindi due pericoli sopra soglia
sulla stessa cella nascono in due esecuzioni che non si conoscono. La coda le
ritrova insieme. Un comune con frana e alluvione nella stessa finestra riceve
una riga che le nomina entrambe, invece di due messaggi che sembrano eventi
distinti.

Il digest non è una via di fuga per la gravità: le classi oltre
``bypass_level`` non entrano mai in coda (lo decide
:func:`~limen.notifications.governance.rate_limit_verdict`), quindi qui non
c'è nulla da riordinare per urgenza — quello che è in coda è, per
costruzione, ciò che poteva aspettare.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD
from limen.data.repos.alert_aggregates_repo import (
    expire_stale,
    fetch_queued,
    mark_sent,
    record_sends,
)
from limen.notifications.base import AlertPayload
from limen.notifications.governance import summarise_digest_it, worst_level

log = get_logger(__name__)


async def run_alert_digest(deps: AppDependencies) -> int:
    """Spedisce un digest se c'è qualcosa in coda. Ritorna i comuni riepilogati.

    Best-effort come ogni job schedulato: un errore viene loggato e non
    propaga, o una coda malformata fermerebbe lo scheduler.
    """
    cfg = deps.settings.notifications.rate_limit
    max_age = timedelta(minutes=cfg.digest_max_age_minutes)
    try:
        # Prima si scade il vecchio: un riepilogo di allerte di ieri non è un
        # ritardo, è disinformazione.
        await expire_stale(max_age=max_age)
        ids, aggregates = await fetch_queued(max_age=max_age)
    except Exception as exc:
        log.error(
            "job.alert_digest.error",
            phase="read",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return 0

    if not aggregates:
        log.debug("job.alert_digest.empty")
        return 0

    testo = summarise_digest_it(aggregates)
    livello = worst_level(aggregates)
    digest_id = f"digest-{uuid.uuid4().hex[:12]}"
    payload = AlertPayload(
        # Il digest è nazionale per costruzione: attraversa le AOI, perché
        # attraversa i pericoli, e ogni pericolo gira per AOI.
        aoi_id="italia",
        hazard_type=DEFAULT_HAZARD,
        max_level=livello,
        max_score=max(a.max_score for a in aggregates),
        summary_it=testo,
        pipeline_version="v1-alert-digest",
        dispatched_at=datetime.now(UTC),
    )

    outcomes: dict[str, bool] = {}
    dispatcher = deps.notification_dispatcher
    if dispatcher is not None:
        outcomes = await dispatcher.dispatch(payload)
    else:
        log.info("job.alert_digest.stub", comuni=len(aggregates), note="no dispatcher")

    try:
        await mark_sent(ids, digest_id=digest_id, channels=outcomes)
        await record_sends(outcomes, kind="digest", aggregates=len(aggregates))
    except Exception as exc:
        # Il messaggio è già uscito: qui si perde solo la tracciabilità, e
        # rilanciare farebbe rispedire lo stesso digest al giro dopo.
        log.error(
            "job.alert_digest.error",
            phase="persist",
            digest_id=digest_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )

    log.info(
        "job.alert_digest.done",
        digest_id=digest_id,
        comuni=len(aggregates),
        level=livello.value,
        outcomes=outcomes,
    )
    return len(aggregates)


__all__ = ["run_alert_digest"]
