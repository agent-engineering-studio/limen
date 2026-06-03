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
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.logging import get_logger
from limen.core.models.context import AggregateAssessment

log = get_logger(__name__)

_PROMPT_PACKAGE = "limen.agents.chat_agents.prompts"
_PROMPT_FILE = "risk_analyst.it.md"


def _load_system_prompt() -> str:
    return resources.files(_PROMPT_PACKAGE).joinpath(_PROMPT_FILE).read_text(encoding="utf-8")


class RiskAnalysis(BaseModel):
    """Structured output schema for :class:`RiskAnalystAgent`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    driver: Literal[
        "static_susceptibility",
        "meteo_trigger",
        "seismic_event",
        "post_fire_destabilization",
        "human_activity",
    ]
    anomalies: list[str] = Field(default_factory=list)
    attention_window_hours: Literal[12, 24, 48, 72]
    confidence: float = Field(..., ge=0.0, le=1.0)


def _summarise_for_prompt(a: AggregateAssessment) -> str:
    top_lines = [
        f"  - cell={c.cell_id} score={c.score:.3f} level={c.level.value} "
        f"s={c.s:.3f} m={c.m:.3f} e={c.e:.3f} f={c.f:.3f} h={c.h:.3f}"
        for c in a.top_cells[:5]
    ]
    return (
        f"AOI: {a.aoi_id}\n"
        f"Horizon: {a.horizon}\n"
        f"Model version: {a.model_version}\n"
        f"Cells scored: {a.n_cells}\n"
        f"High-or-above cells: {a.cells_high_or_above}\n"
        f"Cells by level: {json.dumps(a.cells_by_level)}\n"
        f"Top cells:\n" + "\n".join(top_lines)
    )


def _neutral_fallback(reason: str) -> RiskAnalysis:
    log.warning("risk_analyst.fallback", reason=reason)
    return RiskAnalysis(
        driver="static_susceptibility",
        anomalies=[f"LLM fallback: {reason}"],
        attention_window_hours=24,
        confidence=0.30,
    )


class RiskAnalystAgent:
    """ChatAgent producing a validated :class:`RiskAnalysis`."""

    role_name = "RiskAnalyst"

    def __init__(self, client: ChatClient) -> None:
        self._client = client
        self._system_prompt = _load_system_prompt()

    async def analyse(self, assessment: AggregateAssessment) -> RiskAnalysis:
        user_msg = _summarise_for_prompt(assessment)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=user_msg),
        ]

        raw_first: str | None = None
        try:
            raw_first = await self._client.chat(messages, response_format="json_object")
            return RiskAnalysis.model_validate_json(raw_first)
        except (ValidationError, json.JSONDecodeError) as exc:
            log.warning("risk_analyst.repair_retry", error=str(exc))
        except Exception as exc:  # network etc. — never block the workflow
            return _neutral_fallback(f"chat client error: {type(exc).__name__}: {exc}")

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
            return _neutral_fallback(f"validation failed after retry: {exc}")
        except Exception as exc:
            return _neutral_fallback(f"chat client error during retry: {exc}")
