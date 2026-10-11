"""Il revisore serale: le spiegazioni dell'AI dicono quello che dicono i dati?

Un campione casuale delle spiegazioni scritte nelle ultime 24 ore passa due
controlli (vedi `chat_agents/fedelta.py`): i numeri, deterministico, e un
secondo modello. Il verdetto va accanto alla spiegazione
(`spiegazioni_regione.fedelta`, migrazione 069) e, se è negativo, in un
warning `racconto.infedele`: il revisore non corregge niente, segnala.

Gira **di sera, una volta**, dentro `LLM__SLOW_MODELS_WINDOW_UTC`: il modello
utile qui è GLM-5.2 su colibrì, che a regime scrive un token e mezzo al
secondo e di giorno toglierebbe risorse alla mappa. Non sta nella pipeline
notturna delle 02:00 perché quella è fuori dalla finestra, e il revisore non
deve competere con shadow e retrain per la stessa macchina.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from limen.agents.chat_agents.fedelta import RevisoreFedelta, controllo_numeri
from limen.agents.llm_factory.base import LlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.jobs._tracking import tracked
from limen.api.jobs.ids import JOB_FEDELTA_RACCONTI
from limen.config.settings import SLOW_GENERATION_MODELS, Settings
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


async def controlla_fedelta(settings: Settings, factory: LlmClientFactory) -> dict[str, Any]:
    llm = settings.llm
    modello = llm.models.fedelta.strip()
    # Vuota conta come assente: il compose passa `${LLM__MODELS__FEDELTA:-}`,
    # e una variabile vuota è comunque «dichiarata» per pydantic.
    if "fedelta" not in llm.models.model_fields_set or not modello:
        return {"status": "skipped", "reason": "LLM__MODELS__FEDELTA non dichiarato"}
    lento = modello in SLOW_GENERATION_MODELS
    if lento and not llm.slow_models_allowed(datetime.now(UTC).hour):
        return {"status": "skipped", "reason": "modello lento fuori finestra", "model": modello}

    campione = await spiegazioni_repo.da_giudicare(hours=_FINESTRA_ORE, limite=llm.fedelta_campione)
    if not campione:
        log.info("job.fedelta_racconti.nothing")
        return {"giudicate": 0}

    revisore = RevisoreFedelta(factory.create(RevisoreFedelta.role_name))
    esiti: dict[str, int] = {"fedeli": 0, "infedeli": 0, "senza_giudizio": 0}
    for s in campione:
        if lento and not llm.slow_models_allowed(datetime.now(UTC).hour):
            # La finestra si è chiusa a metà campione: il resto aspetta la
            # sera dopo, invece di occupare la macchina nelle ore della mappa.
            log.info("job.fedelta_racconti.window_closed", remaining=len(campione))
            break
        async with tracked(JOB_FEDELTA_RACCONTI, scope=s.aoi_id) as metrics:
            metrics["hazard"] = s.hazard.value
            numeri = controllo_numeri(s.testo, s.ingresso)
            stile = [v for v in numeri.violations if not v.startswith("numeri non presenti")]
            giudizio = await revisore.giudica(s.testo, s.ingresso)
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
    return await controlla_fedelta(deps.settings, deps.llm_factory)
