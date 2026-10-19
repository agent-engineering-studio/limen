"""Terremoti recenti → scuotimento per cella per il motore (#284).

Legge ciò che il job `limen-ingv-sync` ha già scritto: gli eventi INGV e, per
ognuno con una ShakeMap, la PGA di ogni cella scossa oltre
`seismic.pga_min_g` (`seismic_pga_cella`). Ogni cella riceve solo i
terremoti che l'hanno scossa, con la sua PGA: prima riceveva tutti quelli
d'Italia, con una PGA ricavata dalla sola magnitudo.

Un evento senza ShakeMap non arriva qui: nessuna legge di attenuazione
inventata al posto di quella di INGV.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.risk import SeismicHistoryEvent
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.repos.seismic_repo import scosse_per_cella

log = get_logger(__name__)


class SeismicCheckExecutor(Executor):
    """Carica nel contesto, per cella, i terremoti della finestra che l'hanno scossa."""

    def __init__(self, lookback_days: int | None = None) -> None:
        super().__init__(name="SeismicCheck")
        self._lookback_days = lookback_days

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        cfg = load_regional_thresholds().seismic
        lookback = self._lookback_days or cfg.lookback_days
        end: datetime = ctx.valuation_time
        start = end - timedelta(days=lookback)

        scosse = await scosse_per_cella(
            list(ctx.cell_ids), start, end, min_magnitude=cfg.min_magnitude
        )
        per_cella: dict[str, list[SeismicHistoryEvent]] = {}
        for s in scosse:
            per_cella.setdefault(s.cell_id, []).append(
                SeismicHistoryEvent(
                    event_id=s.event_id,
                    origin_time=s.origin_time,
                    magnitude=s.magnitude,
                    distance_km=s.distanza_km,
                    pga_g=s.pga_g,
                )
            )

        log.info(
            "executor.seismic_check",
            aoi_id=ctx.aoi_id,
            eventi=len({s.event_id for s in scosse}),
            celle_scosse=len(per_cella),
            window_start=start.isoformat(),
            window_end=end.isoformat(),
        )
        return ctx.with_update(
            seismic_per_cella={cella: tuple(eventi) for cella, eventi in per_cella.items()}
        )
