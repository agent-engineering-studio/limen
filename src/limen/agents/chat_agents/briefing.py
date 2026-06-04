"""Briefing ChatAgent — Italian narrative bounded to 150-250 words.

Behaviour:

1. Render the assessment (plus the RiskAnalyst output when present)
   into a compact user message.
2. Call the LLM; count words; if length is inside ``[150, 250]``
   → return.
3. If too short → one regeneration with explicit "extend, do not
   invent numbers" instruction.
4. If too long → soft-trim to the first 250 words (preserves the
   opening narrative).
5. On terminal failure → fall back to a deterministic, schema-bound
   neutral briefing built from the breakdown.
"""

from __future__ import annotations

import asyncio
import re
from importlib import resources

from limen.agents.chat_agents.risk_analyst import RiskAnalysis
from limen.agents.grounding.format import format_citations
from limen.agents.grounding.service import GroundingService
from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.logging import get_logger
from limen.core.models.context import AggregateAssessment
from limen.knowledge.schema import GroundingQuery, GroundingResult

log = get_logger(__name__)

_PROMPT_PACKAGE = "limen.agents.chat_agents.prompts"
_PROMPT_FILE = "briefing.it.md"

MIN_WORDS = 150
MAX_WORDS = 250
# Regex captures word-like runs including hyphenated forms (e.g. "post-incendio").
_WORD_RE = re.compile(r"[\w\-']+", re.UNICODE)


def _load_system_prompt() -> str:
    return resources.files(_PROMPT_PACKAGE).joinpath(_PROMPT_FILE).read_text(encoding="utf-8")


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def trim_to_max(text: str, max_words: int = MAX_WORDS) -> str:
    """Keep the first ``max_words`` words, ending at the previous sentence boundary."""
    words = _WORD_RE.findall(text)
    if len(words) <= max_words:
        return text
    truncated = " ".join(words[:max_words])
    # Snap back to the end of the last sentence punctuation if possible.
    for punct in (". ", "? ", "! "):
        idx = truncated.rfind(punct)
        if idx != -1 and idx > len(truncated) * 0.5:
            return truncated[: idx + 1]
    return truncated + "."


def _fallback_briefing(assessment: AggregateAssessment) -> str:
    """Deterministic Italian briefing built from the breakdown only.

    Used when the LLM call fails or repeatedly produces an out-of-range
    length. It mentions only numbers that are in the assessment.
    """
    top = assessment.top_cells[0] if assessment.top_cells else None
    level = top.level.value if top else "None"
    counts = ", ".join(f"{k}: {v}" for k, v in sorted(assessment.cells_by_level.items()))
    base = (
        f"La valutazione automatica del modello deterministico Limen indica per l'area "
        f"{assessment.aoi_id} una classe dominante {level}. "
        f"Le celle valutate sono {assessment.n_cells}; "
        f"la distribuzione per classe è {{{counts}}}. "
        f"Il contributo statico riflette suscettibilità storica, densità IFFI, "
        f"pendenza, classe PAI e indice litologico; il contributo meteorico "
        f"riflette l'eccesso sulla soglia Caine, l'indice di precipitazione "
        f"antecedente e l'umidità del suolo. La componente sismica considera "
        f"gli eventi con magnitudo significativa nelle ultime giornate; "
        f"la componente post-incendio è attiva solo entro la finestra di amplificazione. "
        f"Le aree più esposte coincidono con i settori a maggiore densità di "
        f"frane storiche e pendenze rilevanti; nei prossimi cicli la diagnosi "
        f"verrà rivalutata con cadenza oraria appoggiandosi alle nuove osservazioni "
        f"meteorologiche e sismologiche disponibili. La diagnosi numerica resta "
        f"autorevole; il presente testo è un riassunto generato in modalità di "
        f"sicurezza in assenza di una risposta valida dal modello narrativo."
    )
    return trim_to_max(base, MAX_WORDS)


class BriefingAgent:
    """Generates the 150-250 word Italian narrative briefing.

    V2.x: when a :class:`GroundingService` is injected, the agent runs
    an advisory KG lookup *in parallel* with the LLM call. The grounding
    result is best-effort — a failure / timeout simply means the
    briefing ships without citations. Numeric scoring outputs are
    NEVER altered by this path.
    """

    role_name = "Briefing"

    def __init__(
        self,
        client: ChatClient,
        *,
        grounding: GroundingService | None = None,
    ) -> None:
        self._client = client
        self._system_prompt = _load_system_prompt()
        self._grounding = grounding

    def _user_message(
        self,
        assessment: AggregateAssessment,
        analysis: RiskAnalysis | None,
    ) -> str:
        top_lines = [
            f"- {c.cell_id} score={c.score:.3f} level={c.level.value}"
            for c in assessment.top_cells[:5]
        ]
        analysis_part = ""
        if analysis is not None:
            analysis_part = (
                "\nAnalisi RiskAnalyst:\n"
                f"- driver: {analysis.driver}\n"
                f"- anomalies: {', '.join(analysis.anomalies) or '(nessuna)'}\n"
                f"- attention_window_hours: {analysis.attention_window_hours}\n"
                f"- confidence: {analysis.confidence:.2f}\n"
            )
        return (
            f"Aoi: {assessment.aoi_id}\n"
            f"Model: {assessment.model_version}\n"
            f"Celle: {assessment.n_cells}; "
            f"high+: {assessment.cells_high_or_above}; "
            f"distribuzione: {assessment.cells_by_level}\n"
            f"Top cells:\n" + "\n".join(top_lines) + analysis_part
        )

    async def brief(
        self,
        assessment: AggregateAssessment,
        analysis: RiskAnalysis | None = None,
    ) -> str:
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=self._user_message(assessment, analysis)),
        ]

        # Kick off the advisory KG lookup CONCURRENTLY so its latency
        # overlaps with the LLM call — it can never extend total budget
        # beyond max(LLM, kg.timeout_seconds). Failures here are
        # swallowed downstream when we render citations.
        grounding_task: asyncio.Task[GroundingResult] | None = None
        if self._grounding is not None and analysis is not None:
            grounding_task = asyncio.create_task(
                self._run_grounding(assessment=assessment, analysis=analysis),
                name="briefing-grounding",
            )

        try:
            text = await self._client.chat(messages)
        except Exception as exc:
            log.warning(
                "briefing.chat_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if grounding_task is not None:
                grounding_task.cancel()
            return _fallback_briefing(assessment)

        words = count_words(text)
        log.info("briefing.length", words=words)

        if MIN_WORDS <= words <= MAX_WORDS:
            return await self._append_citations(text, grounding_task)
        if words > MAX_WORDS:
            return await self._append_citations(trim_to_max(text, MAX_WORDS), grounding_task)

        # Too short → one regeneration with explicit instruction.
        log.info("briefing.regenerate", reason="too_short", words=words)
        extend_msg = ChatMessage(
            role="user",
            content=(
                f"Il briefing precedente era di {words} parole. "
                "Espandi il contenuto fino a stare nell'intervallo 150-250 parole, "
                "**senza introdurre nuovi numeri** non presenti nei dati. "
                "Mantieni stile e regole."
            ),
        )
        try:
            retry = await self._client.chat(
                [*messages, ChatMessage(role="assistant", content=text), extend_msg]
            )
        except Exception as exc:
            log.warning("briefing.retry_error", error=str(exc))
            if grounding_task is not None:
                grounding_task.cancel()
            return _fallback_briefing(assessment)

        retry_words = count_words(retry)
        log.info("briefing.length.retry", words=retry_words)
        if MIN_WORDS <= retry_words <= MAX_WORDS:
            return await self._append_citations(retry, grounding_task)
        if retry_words > MAX_WORDS:
            return await self._append_citations(trim_to_max(retry, MAX_WORDS), grounding_task)
        if grounding_task is not None:
            grounding_task.cancel()
        return _fallback_briefing(assessment)

    # ------------------------------------------------------------------
    # KG grounding — advisory, never authoritative.
    # ------------------------------------------------------------------
    async def _run_grounding(
        self,
        *,
        assessment: AggregateAssessment,
        analysis: RiskAnalysis,
    ) -> GroundingResult:
        """Best-effort KG query. Returns empty result on any failure."""
        if self._grounding is None:
            return GroundingResult(
                query=GroundingQuery(region=assessment.aoi_id, mechanism=analysis.driver),
                passages=(),
            )
        query = GroundingQuery(
            region=assessment.aoi_id,
            mechanism=analysis.driver,
            top_k=self._grounding.settings.top_k,
        )
        try:
            return await self._grounding.ground(query)
        except Exception as exc:
            log.warning(
                "briefing.grounding_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return GroundingResult(query=query, passages=())

    async def _append_citations(
        self,
        narrative: str,
        grounding_task: asyncio.Task[GroundingResult] | None,
    ) -> str:
        """Wait briefly for the KG task, then splice citations in.

        The await is bounded: the task's own internal timeout (set by
        :class:`GroundingService`) already caps the wait. We accept the
        result here even if it's empty — that's the "no citations"
        branch.
        """
        if grounding_task is None:
            return narrative
        try:
            result = await grounding_task
        except asyncio.CancelledError:
            return narrative
        except Exception as exc:
            log.warning(
                "briefing.grounding_task_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return narrative
        block = format_citations(result)
        if not block:
            log.info("briefing.grounding.no_citations")
            return narrative
        log.info("briefing.grounding.cited", passages=len(result.passages))
        return f"{narrative}\n\n{block}"
