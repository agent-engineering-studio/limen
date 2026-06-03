"""Risk-assessment repository (stub).

Interface only. The scoring engine + MAF agents that populate this table
ship in a later prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    cell_id: str
    horizon: str
    score: float
    class_: str
    factors: dict[str, Any]
    explanation: dict[str, Any]
    pipeline_version: str
    computed_at: datetime
    dataset_versions: list[int]


async def insert(_: RiskAssessment) -> int:  # pragma: no cover - stub
    raise NotImplementedError("Risk assessment writes come in a later prompt")


async def latest_for_cell(  # pragma: no cover - stub
    _: str,
    /,
    *,
    horizon: str,
) -> RiskAssessment | None:
    raise NotImplementedError("Risk assessment reads come in a later prompt")
