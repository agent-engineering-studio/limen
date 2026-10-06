"""RiskAnalyst ChatAgent — structured JSON output validated by Pydantic.

Behaviour:

1. Render the engine's :class:`AggregateAssessment` into a compact user
   message.
2. Call the underlying :class:`ChatClient` with ``response_format="json_object"``.
3. Validate the response against :class:`RiskAnalysis`.
4. On invalid JSON, send the parser error back to the model with a
   single "repair" retry.
5. On a second failure, log and return a **neutral fallback**
   (low-confidence ``static_susceptibility`` analysis with 24h window)
   so the workflow keeps running.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from limen.agents.chat_agents.prompts_registry import PROMPT_PACKAGE, prompt_file
from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.logging import get_logger
from limen.core.models.context import AggregateAssessment, CellRiskRecord
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType

log = get_logger(__name__)


@cache
def _load_system_prompt(hazard: HazardType = DEFAULT_HAZARD) -> str:
    """Il prompt del pericolo: ogni pericolo ha le sue cause (#155)."""
    nome = prompt_file("risk_analyst", hazard) or prompt_file("risk_analyst", DEFAULT_HAZARD)
    assert nome is not None
    return resources.files(PROMPT_PACKAGE).joinpath(nome).read_text(encoding="utf-8")


class RiskAnalysis(BaseModel):
    """Structured output schema for :class:`RiskAnalystAgent`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Le cause di ciascun pericolo: le prime cinque sono delle frane, poi
    # alluvione (pioggia, fiume, terreno) e incendio (tempo, combustibile,
    # pendenza). Un pericolo usa solo le sue, e il suo prompt elenca solo
    # quelle.
    driver: Literal[
        "static_susceptibility",
        "meteo_trigger",
        "seismic_event",
        "post_fire_destabilization",
        "human_activity",
        "pluvial_rain",
        "river_discharge",
        "hydraulic_susceptibility",
        "fire_weather",
        "fuel_load",
        "terrain_slope",
    ]
    anomalies: list[str] = Field(default_factory=list)
    attention_window_hours: Literal[12, 24, 48, 72]
    confidence: float = Field(..., ge=0.0, le=1.0)


def _summarise_for_prompt(a: AggregateAssessment) -> str:
    def _components(cell: CellRiskRecord) -> str:
        return " ".join(
            f"{name.lower()}={value:.3f}" for name, value in cell.breakdown.components().items()
        )

    top_lines = [
        f"  - cell={c.cell_id} score={c.score:.3f} level={c.level.value} " + _components(c)
        for c in a.top_cells[:5]
    ]
    return (
        f"AOI: {a.aoi_id}\n"
        f"Hazard: {a.hazard_type.value}\n"
        f"Horizon: {a.horizon}\n"
        f"Model version: {a.model_version}\n"
        f"Cells scored: {a.n_cells}\n"
        f"High-or-above cells: {a.cells_high_or_above}\n"
        f"Cells by level: {json.dumps(a.cells_by_level)}\n"
        f"Top cells:\n" + "\n".join(top_lines)
    )


#: La causa «di fondo» di ciascun pericolo, quella del ripiego neutro.
_DRIVER_NEUTRO: dict[HazardType, str] = {
    HazardType.LANDSLIDE: "static_susceptibility",
    HazardType.FLOOD: "hydraulic_susceptibility",
    HazardType.WILDFIRE: "fuel_load",
}


def _neutral_fallback(reason: str, hazard: HazardType = DEFAULT_HAZARD) -> RiskAnalysis:
    # `llm.fallback` is the single event that says "the engine did not answer
    # and the deterministic path took over". Always a warning, never info: it
    # is how a broken engine is told apart from a working one, and a run that
    # emits it produced a *degraded* analysis while otherwise looking normal.
    log.warning("llm.fallback", role=RiskAnalystAgent.role_name, reason=reason)
    return RiskAnalysis.model_validate(
        {
            "driver": _DRIVER_NEUTRO.get(hazard, "static_susceptibility"),
            "anomalies": [f"LLM fallback: {reason}"],
            "attention_window_hours": 24,
            "confidence": 0.30,
        }
    )


class RiskAnalystAgent:
    """ChatAgent producing a validated :class:`RiskAnalysis`."""

    role_name = "RiskAnalyst"

    def __init__(self, client: ChatClient) -> None:
        self._client = client

    async def analyse(self, assessment: AggregateAssessment) -> RiskAnalysis:
        hazard = assessment.hazard_type
        user_msg = _summarise_for_prompt(assessment)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=_load_system_prompt(hazard)),
            ChatMessage(role="user", content=user_msg),
        ]

        raw_first: str | None = None
        try:
            raw_first = await self._client.chat(messages, response_format="json_object")
            return RiskAnalysis.model_validate_json(raw_first)
        except (ValidationError, json.JSONDecodeError) as exc:
            log.warning("risk_analyst.repair_retry", error=str(exc))
        except Exception as exc:  # network etc. — never block the workflow
            return _neutral_fallback(f"chat client error: {type(exc).__name__}: {exc}", hazard)

        # One repair retry: feed the bad output + the error back to the model.
        repair_msg = ChatMessage(
            role="user",
            content=(
                "Risposta precedente non valida rispetto allo schema. "
                "Rispondi di nuovo con SOLO un oggetto JSON valido."
            ),
        )
        retry_messages = [
            *messages,
            ChatMessage(role="assistant", content=raw_first or ""),
            repair_msg,
        ]
        try:
            raw_retry = await self._client.chat(retry_messages, response_format="json_object")
            return RiskAnalysis.model_validate_json(raw_retry)
        except (ValidationError, json.JSONDecodeError) as exc:
            return _neutral_fallback(f"validation failed after retry: {exc}", hazard)
        except Exception as exc:
            return _neutral_fallback(f"chat client error during retry: {exc}", hazard)
