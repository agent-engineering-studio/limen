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
from collections.abc import Mapping
from functools import cache
from importlib import resources

from rainfall_thresholds.check import check_text

from limen.agents.chat_agents.prompts_registry import PROMPT_PACKAGE, prompt_file
from limen.agents.chat_agents.risk_analyst import RiskAnalysis
from limen.agents.grounding.format import format_citations, senza_citazioni
from limen.agents.grounding.service import GroundingService
from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.affidabilita_iffi import AffidabilitaIffi
from limen.core.grounding_idrogeo import numeri_non_trovati
from limen.core.logging import get_logger
from limen.core.models.context import AggregateAssessment, CellRiskRecord
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import ComponentBreakdown, FloodBreakdown, WildfireBreakdown
from limen.knowledge.schema import GroundingQuery, GroundingResult

log = get_logger(__name__)


# Un racconto che spiega i concetti, non un elenco di numeri: più lungo del
# riassunto di prima, ma ancora leggibile in due minuti.
MIN_WORDS = 220
MAX_WORDS = 400
# Regex captures word-like runs including hyphenated forms (e.g. "post-incendio").
_WORD_RE = re.compile(r"[\w\-']+", re.UNICODE)


@cache
def _load_system_prompt(hazard: HazardType = DEFAULT_HAZARD) -> str:
    """Il prompt del pericolo (#155): una persona da frane che racconta un
    incendio è peggio del silenzio."""
    nome = prompt_file("briefing", hazard) or prompt_file("briefing", DEFAULT_HAZARD)
    assert nome is not None
    return resources.files(PROMPT_PACKAGE).joinpath(nome).read_text(encoding="utf-8")


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


def deterministic_briefing(
    *,
    aoi_id: str,
    n_cells: int,
    cells_by_level: Mapping[str, int],
    dominant_level: str,
    hazard: HazardType = DEFAULT_HAZARD,
    lingua: str = "it",
) -> str:
    """Il briefing ricavato dai soli numeri, senza LLM, in italiano o in inglese.

    Funzione **pura**: nessun log, nessuna rete, stessi argomenti ⇒ stesso
    testo. Ha due chiamanti (#78) e non più uno: la degradazione di
    :class:`BriefingAgent` quando il modello narrativo non risponde, e le API
    che leggono una riga scritta dallo sweep orario, dove ``briefing_it`` è
    NULL per costruzione finché ``briefing_enrichment`` non passa.

    Il corpo è **per pericolo** (#155): un riassunto che parla di soglie
    pluviometriche e frane storiche accanto a un punteggio d'incendio sarebbe
    peggio del silenzio.

    La chiusa dice "senza il modello narrativo" e non "in assenza di una
    risposta valida": ora il caso normale è l'attesa, non il guasto.
    """
    counts = ", ".join(f"{k}: {v}" for k, v in sorted(cells_by_level.items()))
    if lingua == "en":
        return _deterministic_en(aoi_id, n_cells, counts, dominant_level, hazard)
    testa = (
        f"La valutazione automatica del modello deterministico Limen indica per l'area "
        f"{aoi_id} una classe dominante {dominant_level}. "
        f"Le celle valutate sono {n_cells}; "
        f"la distribuzione per classe è {{{counts}}}. "
    )
    coda = (
        "La diagnosi numerica resta autorevole; il presente testo è un riassunto "
        "deterministico, prodotto senza il modello narrativo."
    )
    if hazard is HazardType.FLOOD:
        corpo = (
            "Per gli allagamenti il punteggio guarda avanti: combina la suscettibilità "
            "idraulica del luogo con il più forte fra la pioggia prevista nelle prossime "
            "72 ore e la portata prevista dei fiumi rispetto alla loro piena ordinaria. "
            "Un luogo in alto non si allaga anche se piove a valle, e un fiume di cui non "
            "si conosce la portata non conta come un fiume basso. La valutazione si "
            "aggiorna a ogni ciclo orario con le nuove previsioni; l'allerta che vale è "
            "quella del bollettino della Protezione Civile. "
        )
        return trim_to_max(testa + corpo + coda, MAX_WORDS)
    if hazard is HazardType.WILDFIRE:
        corpo = (
            "Per l'incendio il punteggio è il pericolo meteorologico potenziale: quanto si "
            "propagherebbe un fuoco se partisse, non la probabilità che parta. Nasce "
            "dall'indice FWI, che misura quanto sono secchi i combustibili dopo i giorni "
            "di caldo, vento e pioggia, ed è modulato dal tipo di vegetazione e dalla "
            "pendenza. La valutazione si aggiorna a ogni ciclo orario con il meteo del "
            "giorno. "
        )
        return trim_to_max(testa + corpo + coda, MAX_WORDS)
    base = (
        testa + "Il contributo statico riflette suscettibilità storica, densità IFFI, "
        "pendenza, classe PAI e indice litologico; il contributo meteorico "
        "riflette l'eccesso sulla soglia Caine, l'indice di precipitazione "
        "antecedente e l'umidità del suolo. La componente sismica considera "
        "gli eventi con magnitudo significativa nelle ultime giornate; "
        "la componente post-incendio è attiva solo entro la finestra di amplificazione. "
        "Le aree più esposte coincidono con i settori a maggiore densità di "
        "frane storiche e pendenze rilevanti; nei prossimi cicli la diagnosi "
        "verrà rivalutata con cadenza oraria appoggiandosi alle nuove osservazioni "
        "meteorologiche e sismologiche disponibili. " + coda
    )
    return trim_to_max(base, MAX_WORDS)


def _deterministic_en(
    aoi_id: str, n_cells: int, counts: str, dominant_level: str, hazard: HazardType
) -> str:
    """Lo stesso riassunto deterministico, in inglese, frase per frase."""
    head = (
        f"The automatic assessment of Limen's deterministic model gives the area "
        f"{aoi_id} a dominant class of {dominant_level}. "
        f"{n_cells} cells were assessed; "
        f"the distribution by class is {{{counts}}}. "
    )
    tail = (
        "The numerical diagnosis remains authoritative; this text is a deterministic "
        "summary, produced without the narrative model."
    )
    if hazard is HazardType.FLOOD:
        body = (
            "For floods the score looks ahead: it combines the hydraulic susceptibility "
            "of the place with the stronger of the rain forecast over the next 72 hours "
            "and the forecast river discharge compared with each river's ordinary high "
            "flow. A place on high ground does not flood even if it rains downstream, and "
            "a river whose discharge is unknown does not count as a low river. The "
            "assessment is updated at every hourly cycle with the new forecasts; the "
            "warning that applies is the one in the Civil Protection bulletin. "
        )
    elif hazard is HazardType.WILDFIRE:
        body = (
            "For wildfire the score is the potential weather-driven danger: how far a "
            "fire would spread if it started, not the probability that it starts. It "
            "comes from the FWI index, which measures how dry the fuels are after the "
            "days of heat, wind and rain, and is modulated by vegetation type and slope. "
            "The assessment is updated at every hourly cycle with the day's weather. "
        )
    else:
        body = (
            "The static contribution reflects historical susceptibility, IFFI density, "
            "slope, PAI class and lithological index; the weather contribution reflects "
            "the excess over the Caine threshold, the antecedent precipitation index and "
            "soil moisture. The seismic component considers events of significant "
            "magnitude in recent days; the post-fire component is active only within the "
            "amplification window. The most exposed areas coincide with the sectors with "
            "the highest density of historical landslides and significant slopes; in the "
            "next cycles the diagnosis will be reassessed hourly using the new weather "
            "and seismological observations available. "
        )
    return trim_to_max(head + body + tail, MAX_WORDS)


def _fallback_briefing(assessment: AggregateAssessment, *, reason: str) -> str:
    """:func:`deterministic_briefing` più il log della degradazione.

    Emits ``llm.fallback`` — the same event the RiskAnalyst uses — because the
    return value is indistinguishable from a successful briefing to every
    caller downstream. Without the log there is nothing to tell a healthy
    engine from a dead one.
    """
    log.warning("llm.fallback", role="Briefing", reason=reason)
    return briefing_di_ripiego(assessment)


def briefing_di_ripiego(assessment: AggregateAssessment) -> str:
    """Il testo deterministico di una regione: lo stesso del ripiego.

    Pubblico perché chi salva la spiegazione deve poter dire se il testo che
    ha in mano l'ha scritto il modello o no — da fuori i due sono
    indistinguibili, e la SPA non deve attribuire all'AI un testo suo.
    """
    top = assessment.top_cells[0] if assessment.top_cells else None
    return deterministic_briefing(
        aoi_id=assessment.aoi_id,
        n_cells=assessment.n_cells,
        cells_by_level=assessment.cells_by_level,
        dominant_level=top.level.value if top else "None",
        hazard=assessment.hazard_type,
    )


@cache
def _cod_reg(aoi_id: str) -> int | None:
    """Il codice ISTAT della regione dell'AOI, dal seme; ``None`` se non è una regione."""
    from limen.data.seed.loader import load_regions

    for aoi in load_regions():
        if aoi.id == aoi_id:
            codice = aoi.metadata.get("cod_reg")
            return int(codice) if codice is not None else None
    return None


def affidabilita_regione(assessment: AggregateAssessment) -> AffidabilitaIffi | None:
    """Quanto fidarsi di IFFI nella regione dell'AOI (#669); solo per le frane."""
    from limen.core.affidabilita_iffi import affidabilita_iffi

    if assessment.hazard_type is not HazardType.LANDSLIDE:
        return None
    return affidabilita_iffi("regioni", _cod_reg(assessment.aoi_id))


def nota_affidabilita_iffi(assessment: AggregateAssessment) -> str:
    """Quanto fidarsi di IFFI nella regione (#669), per il racconto delle frane.

    Una riga per il modello, che la riporta come limite del dato: una densità
    IFFI bassa non è una prova di sicurezza. Vuota per gli altri pericoli e
    per un'AOI che non è una regione. Non tocca il punteggio.
    """
    a = affidabilita_regione(assessment)
    if a is None:
        return ""
    return f"\nAffidabilità dell'inventario IFFI: {a.lettura}\n"


def con_fonte_idrogeo(testo: str, affidabilita: AffidabilitaIffi | None, messaggio: str) -> str:
    """Il briefing con la citazione IFFI tra le fonti, e i suoi numeri controllati (#671).

    Solo se il modello ha ricevuto l'affidabilità dell'inventario. La
    citazione è il ``source`` di ispra-idrogeo, non una fonte generica, e va
    nel blocco «Fonti» (che i controlli dei numeri tolgono). I numeri del
    racconto si controllano con ``ispra_idrogeo.grounding.check_text`` contro
    l'affidabilità e il messaggio: uno non trovato finisce in un warning, il
    testo non cambia (decide una persona, come per il revisore).
    """
    if affidabilita is None:
        return testo
    racconto = senza_citazioni(testo)
    non_trovati = numeri_non_trovati(racconto, affidabilita.model_dump(), messaggio)
    if non_trovati:
        log.warning("briefing.idrogeo.numeri_non_trovati", numeri=non_trovati[:10])
    riga = f"- {affidabilita.fonte}"
    if riga in testo:
        return testo
    if racconto == testo:
        return f"{testo}\n\n**Fonti**\n{riga}"
    return f"{testo}\n{riga}"


def _caine_note(cell: CellRiskRecord) -> str:
    """La menzione della soglia Caine, solo dove esiste.

    È una soglia intensità-durata per l'innesco di frane: scriverla accanto a
    un punteggio d'incendio sarebbe rumore, non contesto.
    """
    breakdown = cell.breakdown
    if not isinstance(breakdown, ComponentBreakdown):
        return ""
    superata = "sì" if breakdown.meteo_terms.caine_excess > 0 else "no"
    nota = f" soglia_caine_superata={superata}"
    evento = breakdown.meteo_terms.evento_pioggia
    if evento is None:
        return nota
    return (
        f"{nota} pioggia_evento_mm={evento.cumulata_mm:.0f} durata_evento_h={evento.durata_h:.0f} "
        f"intensita_evento_mm_h={evento.intensita_mm_h:.1f} "
        f"intensita_di_soglia_mm_h={evento.soglia_mm_h:.1f}"
    )


def fatti_pioggia(assessment: AggregateAssessment) -> list[dict[str, float]]:
    """Gli eventi di pioggia che il messaggio dà al modello, con le unità nei nomi.

    Sono i fatti contro cui ``rainfall_thresholds.check`` legge il racconto:
    ogni numero con «mm», «mm/h» o «ore» deve essere uno di questi, arrotondato
    come nel messaggio.
    """
    fatti = []
    for c in assessment.top_cells[:5]:
        b = c.breakdown
        if isinstance(b, ComponentBreakdown) and b.meteo_terms.evento_pioggia is not None:
            e = b.meteo_terms.evento_pioggia
            fatti.append(
                {
                    "cumulated_mm": round(e.cumulata_mm),
                    "duration_h": round(e.durata_h),
                    "intensity_mm_h": round(e.intensita_mm_h, 1),
                    "threshold_intensity_mm_h": round(e.soglia_mm_h, 1),
                }
            )
    return fatti


def controlla_pioggia(testo: str, fatti: list[dict[str, float]], messaggio: str) -> None:
    """Un numero di pioggia del racconto che i fatti non hanno finisce in un warning (#678).

    Come per IdroGEO il testo non cambia: decide una persona.
    """
    if not fatti:
        return
    try:
        sbagliati = check_text(senza_citazioni(testo), fatti, question=messaggio)
    except ValueError as exc:
        # La libreria legge «10.10.26» come un numero e non lo converte: un
        # controllo che dà solo un avviso non deve fermare il racconto.
        log.warning("briefing.pioggia.controllo_fallito", error=str(exc))
        return
    if sbagliati:
        log.warning("briefing.pioggia.numeri_non_trovati", numeri=[m.text for m in sbagliati[:10]])


def _note_pericolo(cell: CellRiskRecord) -> str:
    """I dati grezzi che spiegano il numero, per pericolo.

    Per l'alluvione la pioggia prevista nelle 72 ore e il rapporto di portata
    del fiume (``n.d.`` quando il fiume non è noto, che non vuol dire basso);
    per l'incendio l'indice FWI e il codice di siccità DC. Sono i numeri che
    il prompt chiede di usare: senza, il modello parafraserebbe il punteggio.
    """
    b = cell.breakdown
    if isinstance(b, ComponentBreakdown):
        return _caine_note(cell)
    if isinstance(b, FloodBreakdown):
        pioggia = "n.d." if b.rain_mm is None else f"{b.rain_mm:.0f}"
        fiume = "n.d." if b.discharge_ratio is None else f"{b.discharge_ratio:.2f}"
        return f" pioggia_prevista_72h_mm={pioggia} portata_su_piena_ordinaria={fiume}"
    if isinstance(b, WildfireBreakdown) and b.fire_weather is not None:
        return f" fwi={b.fire_weather.fwi:.1f} dc={b.fire_weather.dc:.0f}"
    return ""


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
        self._grounding = grounding

    def user_message(
        self,
        assessment: AggregateAssessment,
        analysis: RiskAnalysis | None,
    ) -> str:
        top_lines = []
        for c in assessment.top_cells[:5]:
            # Top-3 component drivers + Caine exceedance: anchors the
            # narrative to the quantitative breakdown (issue #2 P2) so the
            # LLM cites real drivers instead of paraphrasing the score.
            drivers = sorted(c.breakdown.components().items(), key=lambda kv: kv[1], reverse=True)[
                :3
            ]
            drivers_txt = ", ".join(f"{name}={value:.2f}" for name, value in drivers)
            top_lines.append(
                f"- {c.cell_id} score={c.score:.3f} level={c.level.value} "
                f"driver=[{drivers_txt}]{_note_pericolo(c)}"
            )
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
            f"Pericolo: {assessment.hazard_type.value}\n"
            f"Model: {assessment.model_version}\n"
            f"Celle: {assessment.n_cells}; "
            f"high+: {assessment.cells_high_or_above}; "
            f"distribuzione: {assessment.cells_by_level}\n"
            f"Top cells:\n"
            + "\n".join(top_lines)
            + analysis_part
            + nota_affidabilita_iffi(assessment)
        )

    async def brief(
        self,
        assessment: AggregateAssessment,
        analysis: RiskAnalysis | None = None,
    ) -> str:
        messaggio = self.user_message(assessment, analysis)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=_load_system_prompt(assessment.hazard_type)),
            ChatMessage(role="user", content=messaggio),
        ]
        affidabilita = affidabilita_regione(assessment)
        pioggia = fatti_pioggia(assessment)

        async def finale(testo: str) -> str:
            controlla_pioggia(testo, pioggia, messaggio)
            con_citazioni = await self._append_citations(testo, grounding_task)
            return con_fonte_idrogeo(con_citazioni, affidabilita, messaggio)

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
            return _fallback_briefing(assessment, reason=f"chat error: {type(exc).__name__}")

        words = count_words(text)
        log.info("briefing.length", words=words)

        if MIN_WORDS <= words <= MAX_WORDS:
            return await finale(text)
        if words > MAX_WORDS:
            return await finale(trim_to_max(text, MAX_WORDS))

        # Too short → one regeneration with explicit instruction.
        log.info("briefing.regenerate", reason="too_short", words=words)
        extend_msg = ChatMessage(
            role="user",
            content=(
                f"Il briefing precedente era di {words} parole. "
                "Espandi il contenuto fino a stare nell'intervallo "
                f"{MIN_WORDS}-{MAX_WORDS} parole, "
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
            return _fallback_briefing(
                assessment, reason=f"chat error on length retry: {type(exc).__name__}"
            )

        retry_words = count_words(retry)
        log.info("briefing.length.retry", words=retry_words)
        if MIN_WORDS <= retry_words <= MAX_WORDS:
            return await finale(retry)
        if retry_words > MAX_WORDS:
            return await finale(trim_to_max(retry, MAX_WORDS))
        if grounding_task is not None:
            grounding_task.cancel()
        return _fallback_briefing(
            assessment, reason=f"still out of range after retry ({retry_words} words)"
        )

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
