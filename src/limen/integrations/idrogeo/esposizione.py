"""L'esposizione ISPRA per comune: chi vive dove la mappa dice frana o alluvione.

Gli indicatori di IdroGEO (`/api/pir/comuni/{codice}`, uno per comune, 7.899)
dal pacchetto ``ispra-idrogeo``: residenti (censimento ISTAT 2021) nelle aree
a pericolosità frana P3+P4 del mosaico PAI 2020-2021 e idraulica media P2 del
mosaico 2020, edifici e imprese.

Una volta al mese e non a richiesta: un'allerta non deve dipendere da
IdroGEO acceso durante un'emergenza, e un backtest vuole un dato fermo. Gira
nel passo notturno, ma le risposte stanno su disco (``LIMEN_DATA_DIR/idrogeo``,
un volume nel container) e si richiedono solo dopo ``MAX_AGE``: la notte
qualunque legge i file in ~2 s, una notte al mese li scarica in ~70 s
(~17 MB). Le scritture si saltano se il contenuto non è cambiato
(``dataset_versions``), come in ogni sync.

Il retry è quello comune: la libreria gira con ``retries=0`` e la chiamata
intera sta in ``call_with_retry``. Un errore a metà non costa i comuni già
salvati, che il tentativo dopo rilegge dal disco.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

from ispra_idrogeo import IdroGEO

from limen.core.logging import get_logger
from limen.data.repos import dataset_versions_repo, esposizione_comuni_repo
from limen.integrations._http import SharedHttpClient, call_with_retry

log = get_logger(__name__)

SOURCE = "ispra"
DATASET = "pir_comuni"
#: Quanto vale una risposta salvata. ISPRA ripubblica i mosaici di rado
#: (PAI 2020-2021, idraulica 2020) e il censimento ogni dieci anni.
MAX_AGE = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class EsposizioneComune:
    istat_code: str
    nome: str
    pop_residenti: int | None
    pop_frana_p3p4: int | None
    pop_frana_p3p4_pct: float | None
    pop_idraulica_p2: int | None
    pop_idraulica_p2_pct: float | None
    edifici: int | None
    imprese: int | None
    indicatori: dict[str, Any]


def cartella() -> Path:
    return Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser() / "idrogeo"


def _intero(valore: Any) -> int | None:
    return int(valore) if isinstance(valore, int | float) else None


def _reale(valore: Any) -> float | None:
    return float(valore) if isinstance(valore, int | float) else None


def da_indicatori(dati: dict[str, Any]) -> EsposizioneComune | None:
    """La riga di un comune; ``None`` se manca il codice."""
    codice = dati.get("uid")
    if not isinstance(codice, int):
        return None
    return EsposizioneComune(
        # ISPRA usa il PRO_COM numerico, `comuni` quello a sei cifre.
        istat_code=f"{codice:06d}",
        nome=str(dati.get("nome") or ""),
        pop_residenti=_intero(dati.get("pop_res021")),
        pop_frana_p3p4=_intero(dati.get("popfr_p3p4")),
        pop_frana_p3p4_pct=_reale(dati.get("popfrp3p4p")),
        pop_idraulica_p2=_intero(dati.get("pop_idr_p2")),
        pop_idraulica_p2_pct=_reale(dati.get("popidp2_p")),
        edifici=_intero(dati.get("ed_tot")),
        imprese=_intero(dati.get("im_tot")),
        indicatori=dati,
    )


async def sync_esposizione(*, max_age: timedelta = MAX_AGE) -> dict[str, Any]:
    """Aggiorna ``esposizione_comuni``; il riepilogo per il passo notturno."""
    idrogeo = IdroGEO(await SharedHttpClient.get(), retries=0)
    dati = await call_with_retry(
        partial(idrogeo.municipalities, "pir", cartella(), max_age=max_age)
    )
    righe = [r for r in (da_indicatori(d) for d in dati) if r is not None]
    if not righe:
        # Un elenco vuoto è un'API che ha risposto male, non l'Italia senza comuni.
        raise RuntimeError("IdroGEO: nessun comune negli indicatori")
    versione = dataset_versions_repo.content_hash(
        [json.dumps(r.indicatori, sort_keys=True, separators=(",", ":")) for r in righe]
    )
    if await dataset_versions_repo.find(SOURCE, DATASET, versione) is not None:
        log.info("esposizione.invariata", comuni=len(righe))
        return {"esito": "invariata", "comuni": len(righe)}
    version_id = await dataset_versions_repo.record(
        source=SOURCE, dataset=DATASET, version=versione, metadata={"comuni": len(righe)}
    )
    scritte = await esposizione_comuni_repo.sostituisci(righe, version_id=version_id)
    frana = sum(r.pop_frana_p3p4 or 0 for r in righe)
    log.info("esposizione.aggiornata", comuni=scritte, residenti_frana_p3p4=frana)
    return {"esito": "aggiornata", "comuni": scritte, "residenti_frana_p3p4": frana}


__all__ = ["MAX_AGE", "EsposizioneComune", "cartella", "da_indicatori", "sync_esposizione"]
