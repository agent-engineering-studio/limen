"""A2A skills — the read-only ``limen-ops`` tools, exposed to other agents.

Each skill maps 1:1 to a function in :mod:`limen.mcp.tools` (single source of
truth for the queries — nothing is duplicated). A client selects a skill by
putting ``{"skill": "<id>", "params": {...}}`` in a ``DataPart`` or in the
message ``metadata``; with neither, the server defaults to ``national_report``
(a safe, deterministic overview). Mutating tools (``run_monitor``,
``build_report``) stay MCP-only, admin-token gated — A2A is query interop.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from limen.a2a.models import Message
from limen.mcp import tools

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    handler: Handler
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


async def _risk_summary(p: dict[str, Any]) -> Any:
    return await tools.risk_summary(p.get("aoi_id"))


async def _top_risk_cells(p: dict[str, Any]) -> Any:
    return await tools.top_risk_cells(limit=int(p.get("limit", 10)), aoi_id=p.get("aoi_id"))


async def _cell_breakdown(p: dict[str, Any]) -> Any:
    cell_id = p.get("cell_id")
    if not isinstance(cell_id, str) or not cell_id:
        raise ValueError("cell_breakdown requires a 'cell_id' string param")
    return await tools.cell_breakdown(cell_id)


async def _recent_alerts(p: dict[str, Any]) -> Any:
    return await tools.recent_alerts(
        threshold=str(p.get("threshold", "Moderate")),
        since_hours=int(p.get("since_hours", 24)),
        limit=int(p.get("limit", 50)),
    )


async def _national_report(_: dict[str, Any]) -> Any:
    return await tools.national_report()


SKILLS: dict[str, Skill] = {
    s.id: s
    for s in (
        Skill(
            id="national_report",
            name="Quadro nazionale",
            description="Sintesi aggregata del rischio frane/inondazioni per l'Italia "
            "(regioni, celle a rischio più alto, shadow ML, allerte 24h) con testo "
            "pronto in italiano (report_it).",
            handler=_national_report,
            tags=("landslide", "flood", "report", "italy"),
            examples=("Che situazione c'è oggi in Italia?",),
        ),
        Skill(
            id="risk_summary",
            name="Sintesi per regione",
            description="Ultimo assessment per regione: celle per classe, punteggio "
            "massimo, quando. Passa 'aoi_id' (es. it-puglia) per una sola regione.",
            handler=_risk_summary,
            tags=("landslide", "flood", "region"),
            examples=("Riepilogo rischio per it-basilicata",),
        ),
        Skill(
            id="top_risk_cells",
            name="Celle a rischio più alto",
            description="Classifica nazionale (o per 'aoi_id') delle celle da 1 km² con "
            "punteggio più alto. Parametri: 'limit' (default 10), 'aoi_id'.",
            handler=_top_risk_cells,
            tags=("landslide", "flood", "ranking"),
            examples=("Le 5 celle più a rischio in Italia",),
        ),
        Skill(
            id="cell_breakdown",
            name="Scomposizione di una cella",
            description="Scomposizione per componente (S/M/E/F/H/K) + briefing italiano "
            "di una cella. Richiede 'cell_id'.",
            handler=_cell_breakdown,
            tags=("landslide", "flood", "explain"),
            examples=("Perché la cella it-puglia|12|34 è a rischio?",),
        ),
        Skill(
            id="recent_alerts",
            name="Allerte recenti",
            description="Celle al/sopra una soglia nella finestra recente. Parametri: "
            "'threshold' (Moderate|High|VeryHigh), 'since_hours', 'limit'.",
            handler=_recent_alerts,
            tags=("landslide", "flood", "alerts"),
            examples=("Allerte High delle ultime 12 ore",),
        ),
    )
}

DEFAULT_SKILL = "national_report"


def resolve_invocation(message: Message) -> tuple[str, dict[str, Any]]:
    """Pick the skill id + params from a message (DataPart → metadata → default)."""
    for part in message.parts:
        if part.kind == "data":
            picked = _from_mapping(part.data)
            if picked is not None:
                return picked
    picked = _from_mapping(message.metadata or {})
    if picked is not None:
        return picked
    return DEFAULT_SKILL, {}


def _from_mapping(data: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    skill = data.get("skill")
    if isinstance(skill, str) and skill in SKILLS:
        params = data.get("params")
        return skill, params if isinstance(params, dict) else {}
    return None
