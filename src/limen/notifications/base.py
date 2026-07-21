"""Notification Protocol + channel-agnostic :class:`AlertPayload`.

The payload is built once per workflow tick from the deterministic
:class:`AggregateAssessment` and the operator-prioritised cells. The
dispatcher hands the same payload to every channel; each channel
renders it for its medium (HTML/text for email, plain HTML for
Telegram, JSON for MQTT).

Acceptance criterion §1 (no business logic in endpoints / channels):
channel implementations only serialise / transport. Selection of
which cells to include + ranking by priority happens upstream in the
``AlertDispatchExecutor``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from limen.config.settings import AlertSettings
from limen.core.models.context import AggregateAssessment, CellRiskRecord
from limen.core.models.risk import RiskLevel

_LEVEL_RANK = {
    RiskLevel.None_: 0,
    RiskLevel.Low: 1,
    RiskLevel.Moderate: 2,
    RiskLevel.High: 3,
    RiskLevel.VeryHigh: 4,
}
_LEVEL_LABEL_IT = {
    RiskLevel.None_: "nessuno",
    RiskLevel.Low: "basso",
    RiskLevel.Moderate: "moderato",
    RiskLevel.High: "alto",
    RiskLevel.VeryHigh: "molto alto",
}


class AlertedCell(BaseModel):
    """One cell entry inside :class:`AlertPayload`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cell_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    level: RiskLevel
    priority: float = Field(..., ge=0.0)
    map_url: str | None = None
    # Comune (ISTAT) name for context — enriched by the dispatch executor.
    comune: str | None = None


class AlertPayload(BaseModel):
    """Channel-agnostic alert envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    aoi_id: str
    max_level: RiskLevel
    max_score: float = Field(..., ge=0.0, le=1.0)
    cells: list[AlertedCell] = Field(default_factory=list)
    summary_it: str
    map_url: str | None = None
    pipeline_version: str
    dispatched_at: datetime

    @property
    def cell_count(self) -> int:
        return len(self.cells)


@runtime_checkable
class NotificationChannel(Protocol):
    """Minimal channel contract.

    Implementations:

    * MUST be safe to construct even when their dependency SDK / config
      is missing (use lazy imports + an ``is_enabled`` guard).
    * MUST NOT raise from :meth:`send` on transport failures — return
      ``False`` instead and log. The dispatcher's safety net catches
      anything that does escape, but well-behaved channels keep that
      net unused.
    """

    @property
    def name(self) -> str:
        """Short identifier (``"telegram"``, ``"mqtt"``, ``"email"``)."""

    @property
    def is_enabled(self) -> bool:
        """``True`` when the channel has the config it needs to send."""

    async def send(self, payload: AlertPayload) -> bool:
        """Deliver ``payload``. Returns ``True`` on success."""


def _cell_map_url(*, base: str, aoi_id: str, cell_id: str) -> str:
    base_clean = base.rstrip("/")
    return f"{base_clean}/?{urlencode({'aoi': aoi_id, 'cell': cell_id})}"


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def _format_summary_it(
    *,
    assessment: AggregateAssessment,
    top_cells: list[CellRiskRecord],
    max_words: int = 80,
) -> str:
    """Build a ≤80-word Italian summary.

    Uses only numbers already present in the assessment / top cells —
    no LLM, no figures invented. The result is deterministic so tests
    can assert on it.
    """
    n_high = assessment.cells_high_or_above
    counts = ", ".join(f"{lvl}: {n}" for lvl, n in sorted(assessment.cells_by_level.items()))
    top_id = top_cells[0].cell_id if top_cells else "—"
    top_score = top_cells[0].score if top_cells else 0.0
    top_level = top_cells[0].level if top_cells else assessment.cells_by_level
    top_level_label = (
        _LEVEL_LABEL_IT.get(top_level, str(top_level))
        if isinstance(top_level, RiskLevel)
        else "n/d"
    )
    text = (
        f"Limen — allerta {top_level_label} per AOI {assessment.aoi_id}: "
        f"{n_high} celle a livello alto o superiore "
        f"(distribuzione {counts}). Cella di picco {top_id} "
        f"con punteggio {top_score:.2f}. Diagnosi prodotta dal modello "
        f"deterministico {assessment.model_version}. "
        f"Briefing operativo completo nella scheda della cella."
    )
    return _truncate_words(text, max_words)


def build_alert_payload(
    *,
    assessment: AggregateAssessment,
    prioritised: list[tuple[CellRiskRecord, float]],
    settings: AlertSettings,
    dispatched_at: datetime,
    comuni: dict[str, str] | None = None,
) -> AlertPayload:
    """Assemble an :class:`AlertPayload`.

    Args:
        assessment: The full AOI-level assessment from the workflow.
        prioritised: Pairs ``(cell, priority)`` sorted in descending
            priority order by the executor.
        settings: Active :class:`AlertSettings` (used for ``map_base_url``
            and ``top_k``).
        dispatched_at: Wall-clock time the dispatch starts; included in
            the payload so channels can stamp the human-facing message.
    """
    take = prioritised[: settings.top_k]
    comuni = comuni or {}
    cells = [
        AlertedCell(
            cell_id=record.cell_id,
            score=record.score,
            level=record.level,
            priority=priority,
            map_url=_cell_map_url(
                base=settings.map_base_url,
                aoi_id=assessment.aoi_id,
                cell_id=record.cell_id,
            ),
            comune=comuni.get(record.cell_id),
        )
        for record, priority in take
    ]
    top_record = take[0][0] if take else None
    max_level = top_record.level if top_record is not None else RiskLevel.None_
    max_score = top_record.score if top_record is not None else 0.0
    summary = _format_summary_it(
        assessment=assessment,
        top_cells=[r for r, _ in take],
    )

    map_url = settings.map_base_url.rstrip("/")
    if assessment.aoi_id:
        map_url = f"{map_url}/?{urlencode({'aoi': assessment.aoi_id})}"

    return AlertPayload(
        aoi_id=assessment.aoi_id,
        max_level=max_level,
        max_score=max_score,
        cells=cells,
        summary_it=summary,
        map_url=map_url,
        pipeline_version=assessment.pipeline_version,
        dispatched_at=dispatched_at,
    )


def level_at_least(level: RiskLevel, threshold: RiskLevel) -> bool:
    """Return whether ``level`` is at or above ``threshold``."""
    return _LEVEL_RANK[level] >= _LEVEL_RANK[threshold]


__all__ = [
    "AlertPayload",
    "AlertedCell",
    "NotificationChannel",
    "build_alert_payload",
    "level_at_least",
]
