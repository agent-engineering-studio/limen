"""``limen fwi-confronto`` — la nostra catena FWI contro quella ufficiale (#280).

Due riferimenti, entrambi Copernicus e aperti:

* **EWDS** `cems-fire-historical-v1`: la catena calcolata su ERA5, 0,25°, fino
  a ~3 giorni fa. Serve ``COPERNICUS__EWDS_KEY`` (la stessa del GloFAS) e il
  gruppo di dipendenze ``copernicus``; gira sull'host.
* **EFFIS** WMS `mf010.*`: la catena calcolata sul meteo di Météo-France,
  pubblica, fino a dopodomani.

Per ogni componente (FWI, FFMC, DMC, DC, ISI, BUI) il report dà scarto medio
(nostro meno ufficiale), errore assoluto e quadratico, correlazione; per l'FWI
anche la quota di giorni-nodo nella stessa classe di pericolo e quella in cui
la nostra classe è più alta. Solo i giorni che il motore considera assestati
(`FwiBlock.in_assestamento`, la stessa regola). Non scrive niente: è una misura.
Un riferimento che non risponde si salta e lo si dice, senza fermare l'altro.

Variabili d'ambiente:

* ``LIMEN_FWI_CONFRONTO_INIZIO`` / ``_FINE`` — date ISO; di default gli
  ultimi 30 giorni fino a 5 giorni fa (il ritardo dello storico EWDS).
* ``LIMEN_FWI_CONFRONTO_FONTE`` — ``ewds``, ``effis`` o ``entrambe`` (default).
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds
from limen.core.scoring.wildfire.confronto import Esito, confronta
from limen.data.db import lifespan_pool
from limen.data.repos.fwi_state_repo import GiornoCatena, catena_fra
from limen.integrations._http import SharedHttpClient
from limen.integrations.copernicus import ewds_fwi
from limen.integrations.copernicus.ewds_glofas import nuovo_client
from limen.integrations.effis.fwi_wms import COMPONENTI, fwi_ufficiale

log = get_logger(__name__)

_INIZIO_ENV = "LIMEN_FWI_CONFRONTO_INIZIO"
_FINE_ENV = "LIMEN_FWI_CONFRONTO_FINE"
_FONTE_ENV = "LIMEN_FWI_CONFRONTO_FONTE"
#: Il ritardo dello storico EWDS per questo dataset: il 19 ottobre 2026 il
#: file di ottobre arrivava al 14. Più di `LATENZA_STORICO_GIORNI` del GloFAS.
_RITARDO_EWDS_GIORNI = 5

Chiave = tuple[tuple[float, float], date]


def _data(nome: str, default: date) -> date:
    grezza = os.getenv(nome)
    if not grezza:
        return default
    try:
        return date.fromisoformat(grezza)
    except ValueError:
        log.warning("fwi_confronto.env_non_valida", var=nome, valore=grezza, uso=str(default))
        return default


def coppie(
    nostri: list[GiornoCatena], riferimento: dict[Chiave, dict[str, float]]
) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for g in nostri:
        rif = riferimento.get(((g.lon, g.lat), g.day))
        if rif is None:
            continue
        for componente, valore in g.componenti.items():
            if componente in rif:
                out[componente].append((valore, rif[componente]))
    return dict(out)


def _ewds(nostri: list[GiornoCatena], inizio: date, fine: date) -> dict[Chiave, dict[str, float]]:
    s = get_settings().copernicus
    if s.ewds_key is None or not s.ewds_key.get_secret_value():
        log.warning("fwi_confronto.ewds_senza_chiave", variabile="COPERNICUS__EWDS_KEY")
        return {}
    try:
        client = nuovo_client(s.ewds_url, s.ewds_key.get_secret_value())
        files = ewds_fwi.scarica(Path(s.cartella) / "fwi", inizio, fine, client=client)
        nodi = sorted({(g.lon, g.lat) for g in nostri})
        return ewds_fwi.valori_per_nodo(files, nodi)
    except Exception as exc:
        # Licenza non accettata, coda, rete: è una lettura, l'altro
        # riferimento deve girare lo stesso.
        log.warning("integration.degraded", label="ewds.fwi", error_type=type(exc).__name__)
        return {}


async def _effis(nostri: list[GiornoCatena]) -> dict[Chiave, dict[str, float]]:
    per_giorno: dict[date, set[tuple[float, float]]] = defaultdict(set)
    for g in nostri:
        per_giorno[g.day].add((g.lon, g.lat))
    out: dict[Chiave, dict[str, float]] = defaultdict(dict)
    for giorno, insieme in sorted(per_giorno.items()):
        nodi = sorted(insieme)
        for componente in COMPONENTI:
            valori = await fwi_ufficiale(giorno, nodi, componente)
            if valori is None:
                continue
            for nodo, v in valori.items():
                out[(nodo, giorno)][componente] = v
    # EFFIS dipinge il mare a zero: un nodo sulla costa che cade su un pixel di
    # mare leggerebbe zero in ogni componente. Un FFMC esattamente nullo a
    # terra non esiste (parte da 85 e non scende sotto qualche unità), quindi
    # è la maschera: quel nodo-giorno non è un dato.
    return {k: v for k, v in out.items() if v.get("ffmc", 0.0) > 0.0}


def _riporta(fonte: str, esiti: list[Esito]) -> None:
    if not esiti:
        log.warning("fwi_confronto.nessuna_coppia", fonte=fonte)
    for e in esiti:
        log.info(
            "fwi_confronto.esito",
            fonte=fonte,
            componente=e.componente,
            n=e.n,
            bias=round(e.bias, 2),
            mae=round(e.mae, 2),
            rmse=round(e.rmse, 2),
            r=None if e.r is None else round(e.r, 3),
            stessa_classe=None if e.stessa_classe is None else round(e.stessa_classe, 3),
            classe_piu_alta=None if e.sopra is None else round(e.sopra, 3),
        )


async def run() -> int:
    soglie = load_hazard_thresholds(HazardType.WILDFIRE)
    if not isinstance(soglie, WildfireThresholds):
        log.error("fwi_confronto.config", got=type(soglie).__name__)
        return 1
    oggi = datetime.now(UTC).date()
    fine = _data(_FINE_ENV, oggi - timedelta(days=_RITARDO_EWDS_GIORNI))
    inizio = _data(_INIZIO_ENV, fine - timedelta(days=29))
    fonte = os.getenv(_FONTE_ENV, "entrambe")
    if fonte not in ("ewds", "effis", "entrambe"):
        log.warning("fwi_confronto.env_non_valida", var=_FONTE_ENV, valore=fonte, uso="entrambe")
        fonte = "entrambe"

    async with lifespan_pool():
        tutti = await catena_fra(inizio, fine)
    # Confrontare l'avvio con una catena che parte dal 1940 misurerebbe l'avvio.
    nostri = [g for g in tutti if not soglie.fwi.in_assestamento(g.day, g.chain_days)]
    log.info("fwi_confronto.assestamento", esclusi=len(tutti) - len(nostri))
    log.info("fwi_confronto.nostri", giorni_nodo=len(nostri), inizio=str(inizio), fine=str(fine))
    if not nostri:
        log.warning("fwi_confronto.catena_vuota", suggerimento="limen fwi-backfill")
        return 0

    mx, classi = soglie.fwi.normalisation_max, soglie.classes
    try:
        if fonte in ("ewds", "entrambe"):
            riferimento = _ewds(nostri, inizio, fine)
            esiti = confronta(coppie(nostri, riferimento), normalisation_max=mx, cutoffs=classi)
            _riporta("ewds", esiti)
        if fonte in ("effis", "entrambe"):
            riferimento = await _effis(nostri)
            esiti = confronta(coppie(nostri, riferimento), normalisation_max=mx, cutoffs=classi)
            _riporta("effis", esiti)
    finally:
        await SharedHttpClient.aclose()
    return 0


__all__ = ["coppie", "run"]
