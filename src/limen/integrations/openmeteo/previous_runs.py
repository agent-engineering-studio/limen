"""Le corse passate dei modelli meteo, con il loro anticipo.

Solo l'API pubblica «previous runs» le conserva: la nostra istanza tiene la
corsa più recente, che per addestrare un correttore non basta — serve la
previsione **com'era quando è stata emessa**. È quindi un consumo del tetto
pubblico, ed è fatto per girare a lotti e a più riprese (#155, punto 1).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

import httpx

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"

#: I modelli confrontati: due regionali ad alta risoluzione, due globali e il
#: modello a reti neurali di ECMWF. AIFS c'è solo dal 2025: prima i suoi
#: valori mancano, e il correttore lo sa trattare.
MODELLI: tuple[str, ...] = (
    "icon_seamless",
    "meteofrance_seamless",
    "ecmwf_ifs025",
    "gfs_seamless",
    "ecmwf_aifs025_single",
)

#: Quanti nodi servono al correttore della pioggia prima di addestrarlo sul
#: serio: il campione che `limen rain-ensemble fetch` raccoglie a lotti.
NODI_CORRETTORE = 150

#: Come si chiamano per chi legge la mappa. AIFS è anch'esso intelligenza
#: artificiale — una rete neurale addestrata sulle rianalisi — e va detto.
NOMI: dict[str, str] = {
    "icon_seamless": "ICON (DWD, Germania)",
    "meteofrance_seamless": "Météo-France",
    "ecmwf_ifs025": "ECMWF IFS",
    "gfs_seamless": "GFS (NOAA, USA)",
    "ecmwf_aifs025_single": "ECMWF AIFS (rete neurale)",
}

#: Anticipo in giorni → variabile. Niente anticipo 0 (la corsa più recente):
#: il correttore non lo usa, e oltre dieci serie l'API pubblica conta ogni
#: richiesta come più chiamate sul tetto che serve anche a GloFAS.
VARIABILI: dict[int, str] = {
    1: "precipitation_previous_day1",
    2: "precipitation_previous_day2",
    3: "precipitation_previous_day3",
}


class QuotaEsauritaError(Exception):
    """L'API pubblica ha risposto 429: si riprende domani."""


async def previsioni_giornaliere(
    *, lon: float, lat: float, inizio: date, fine: date
) -> dict[tuple[str, int], dict[date, float]]:
    """Per (modello, anticipo), la pioggia prevista di ogni giorno.

    Un giorno entra solo se ha tutte e 24 le ore: una somma su un giorno
    bucato sembrerebbe un giorno asciutto.
    """
    params: dict[str, Any] = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start_date": inizio.isoformat(),
        "end_date": fine.isoformat(),
        "hourly": ",".join(VARIABILI.values()),
        "models": ",".join(MODELLI),
        "timezone": "UTC",
    }
    try:
        resp = await fetch_with_retry(
            "GET", PREVIOUS_RUNS_URL, client=await SharedHttpClient.get(), params=params
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise QuotaEsauritaError(str(exc)) from exc
        raise
    orario = resp.json().get("hourly") or {}
    tempi = [datetime.fromisoformat(t).date() for t in orario.get("time", [])]
    out: dict[tuple[str, int], dict[date, float]] = {}
    for modello in MODELLI:
        for lead, variabile in VARIABILI.items():
            valori = orario.get(f"{variabile}_{modello}") or []
            somme: dict[date, float] = defaultdict(float)
            ore: dict[date, int] = defaultdict(int)
            for giorno, v in zip(tempi, valori, strict=False):
                if v is not None:
                    somme[giorno] += float(v)
                    ore[giorno] += 1
            completi = {g: max(s, 0.0) for g, s in somme.items() if ore[g] == 24}
            if completi:
                out[(modello, lead)] = completi
    return out
