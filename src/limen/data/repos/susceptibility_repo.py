"""Susceptibility repository (stub).

Interface only. Susceptibility model + writes ship in a later prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CellSusceptibility:
    cell_id: str
    score: float
    class_: str
    model_version: str
    inputs: dict[str, Any]


async def upsert(_: CellSusceptibility) -> None:  # pragma: no cover - stub
    raise NotImplementedError("Susceptibility writes come in a later prompt")


async def get_for_cell(_: str) -> CellSusceptibility | None:  # pragma: no cover - stub
    raise NotImplementedError("Susceptibility reads come in a later prompt")
