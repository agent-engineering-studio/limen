"""Il revisore serale: le spiegazioni dell'AI dicono quello che dicono i dati?

Un campione casuale delle spiegazioni scritte nelle ultime 24 ore passa due
controlli (vedi `chat_agents/fedelta.py`): i numeri, deterministico, e un
secondo modello. Il verdetto va accanto alla spiegazione
(`spiegazioni_regione.fedelta`, migrazione 069) e, se è negativo, in un
warning `racconto.infedele`: il revisore non corregge niente, segnala.

Gira **di sera, una volta**, a `LLM__FEDELTA_ORA_UTC`: tutto il campione va
in un solo Message Batch di Claude, e il job aspetta che finisca. Sulla
macchina non pesa niente; prima girava su GLM-5.2 in locale (colibrì), che
chiedeva 21 GB di RAM e venti minuti per giudizio.
"""

from __future__ import annotations

from typing import Any

from limen.agents.chat_agents.fedelta import RevisoreFedelta, controllo_numeri
from limen.api.dependencies import AppDependencies
from limen.api.jobs._tracking import tracked
from limen.api.jobs.ids import JOB_FEDELTA_RACCONTI
from limen.config.settings import Settings
from limen.core.logging import get_logger
from limen.data.repos import spiegazioni_repo

log = get_logger(__name__)

# Le spiegazioni si rileggono finché sono quelle sulla mappa: oltre un giorno
# `briefing_enrichment` le ha riscritte (LLM__BRIEFING_MIN_HOURS = 24).
_FINESTRA_ORE = 24


def verdetto(*, numeri_sconosciuti: list[str], giudizio: dict[str, Any] | None) -> bool | None:
    """``False`` se un controllo ha trovato un problema, ``True`` se tutti e
    due l'hanno escluso, ``None`` se il revisore non ha risposto e i numeri
    tornano: «non so» non è «fedele».

    Lo stile (lunghezza, elenchi, termini d'allarme) non entra nel verdetto:
    un testo di 260 parole è lungo, non infedele.
    """
    if numeri_sconosciuti:
        return False
    if giudizio is None:
        return None
    return bool(giudizio["fedele"])


async def controlla_fedelta(settings: Settings) -> dict[str, Any]:
    llm = settings.llm
    modello = llm.models.fedelta.strip()
    # Vuota conta come assente: il compose passa `${LLM__MODELS__FEDELTA:-}`,
    # e una variabile vuota è comunque «dichiarata» per pydantic.
    if "fedelta" not in llm.models.model_fields_set or not modello:
        return {"status": "skipped", "reason": "LLM__MODELS__FEDELTA non dichiarato"}
    chiave = settings.anthropic_api_key
    # Anche qui il compose passa `${ANTHROPIC_API_KEY:-}`: vuota è assente.
    if chiave is None or not chiave.get_secret_value().strip():
        return {"status": "skipped", "reason": "ANTHROPIC_API_KEY assente", "model": modello}

    campione = await spiegazioni_repo.da_giudicare(hours=_FINESTRA_ORE, limite=llm.fedelta_campione)
    if not campione:
        log.info("job.fedelta_racconti.nothing")
        return {"giudicate": 0}

    revisore = RevisoreFedelta(
        api_key=chiave,
        model=modello,
        attesa_massima_s=llm.fedelta_attesa_massima_minuti * 60,
    )
    giudizi = await revisore.giudica([(s.testo, s.ingresso) for s in campione])
    esiti: dict[str, int] = {"fedeli": 0, "infedeli": 0, "senza_giudizio": 0}
    for s, giudizio in zip(campione, giudizi, strict=True):
        async with tracked(JOB_FEDELTA_RACCONTI, scope=s.aoi_id) as metrics:
            metrics["hazard"] = s.hazard.value
            numeri = controllo_numeri(s.testo, s.ingresso)
            stile = [v for v in numeri.violations if not v.startswith("numeri non presenti")]
            giudizio_dict = giudizio.model_dump() if giudizio is not None else None
            fedele = verdetto(numeri_sconosciuti=numeri.unknown_numbers, giudizio=giudizio_dict)
            scritto = await spiegazioni_repo.scrivi_fedelta(
                aoi_id=s.aoi_id,
                hazard=s.hazard,
                scritta=s.scritta,
                fedelta={
                    "fedele": fedele,
                    "numeri_sconosciuti": numeri.unknown_numbers,
                    "stile": stile,
                    "revisore": modello,
                    "giudizio": giudizio_dict,
                    "autore": s.modello,
                },
            )
            metrics.update(
                {"fedele": fedele, "scritto": scritto, "numeri_sconosciuti": numeri.unknown_numbers}
            )
            if not scritto:
                # Il briefing ha riscritto la spiegazione mentre il revisore la
                # leggeva: il giudizio è su un testo che non esiste più, e un
                # allarme di infedeltà senza verdetto salvato non si può seguire.
                continue
            if fedele is False:
                log.warning(
                    "racconto.infedele",
                    aoi_id=s.aoi_id,
                    hazard=s.hazard.value,
                    autore=s.modello,
                    numeri_sconosciuti=numeri.unknown_numbers,
                    problemi=(giudizio_dict or {}).get("problemi", []),
                )
                esiti["infedeli"] += 1
            elif fedele is None:
                esiti["senza_giudizio"] += 1
            else:
                esiti["fedeli"] += 1
    log.info("job.fedelta_racconti.summary", model=modello, **esiti)
    return {"giudicate": sum(esiti.values()), **esiti}


async def run_fedelta_racconti(deps: AppDependencies) -> dict[str, Any]:
    return await controlla_fedelta(deps.settings)
