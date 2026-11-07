"""Come stanno le fonti esterne: l'ultimo successo e l'ultimo errore (#408).

Il 3 novembre 2026 Open-Meteo pubblico ha risposto 429 per ore e l'incendio è
stato «non misurato» su tutta l'Italia: lo dicevano solo i log del worker. Ogni
chiamata passa da :func:`limen.integrations._http.fetch_with_retry`, che qui
annota l'esito per fonte, riconosciuta dall'host; il battito del worker
riversa il registro in ``salute_fonti`` (migrazione 088) e la pagina «Salute»
lo legge.

Il registro è del processo e si svuota a ogni riversamento: costa un dizionario
per chiamata, nessuna scrittura sul database nel percorso della richiesta. Un
4xx che non è un 429 non è un guasto della fonte (un fotogramma radar scaduto
risponde 404 per costruzione) e non si annota.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from urllib.parse import urlsplit

from limen.core.models.hazard import HazardType


@dataclass(frozen=True, slots=True)
class Fonte:
    id: str
    nome: str
    pericoli: tuple[HazardType, ...]


_TUTTI = (HazardType.LANDSLIDE, HazardType.FLOOD, HazardType.WILDFIRE)

#: Le fonti che la pagina conosce. Una chiamata a un host che non è qui non si
#: annota: la pagina dice dei dati che muovono la mappa, non di ogni URL.
FONTI: dict[str, Fonte] = {
    f.id: f
    for f in (
        Fonte("openmeteo_locale", "Open-Meteo locale (meteo e previsioni)", _TUTTI),
        Fonte("openmeteo", "Open-Meteo pubblico", _TUTTI),
        Fonte("glofas", "GloFAS via Open-Meteo (portata dei fiumi)", (HazardType.FLOOD,)),
        Fonte("dpc", "Radar DPC (pioggia osservata)", (HazardType.FLOOD, HazardType.WILDFIRE)),
        Fonte("effis", "EFFIS (incendi e FWI europeo)", (HazardType.WILDFIRE,)),
        Fonte("firms", "NASA FIRMS (fuochi attivi)", (HazardType.WILDFIRE,)),
        Fonte("ingv", "INGV (terremoti)", (HazardType.LANDSLIDE,)),
    )
}


@dataclass(slots=True)
class Esito:
    ultimo_ok: datetime | None = None
    ultimo_errore: datetime | None = None
    errore: str | None = None


_REGISTRO: dict[str, Esito] = {}


@cache
def _host_open_meteo_locali() -> frozenset[str]:
    from limen.config.settings import get_settings

    om = get_settings().openmeteo
    urls = (om.forecast_url, om.archive_url)
    return frozenset(h for u in urls if u and (h := urlsplit(str(u)).hostname))


def fonte_di(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("flood-api.") and host.endswith("open-meteo.com"):
        return "glofas"
    if host in _host_open_meteo_locali():
        return "openmeteo_locale"
    if host.endswith("open-meteo.com"):
        return "openmeteo"
    if host.endswith("protezionecivile.gov.it") or host.endswith("protezionecivile.it"):
        return "dpc"
    if "effis" in host:
        return "effis"
    if "firms" in host or host.endswith("earthdata.nasa.gov"):
        return "firms"
    if host.endswith("ingv.it"):
        return "ingv"
    return None


def messaggio(*, stato_http: int | None = None, eccezione: BaseException | None = None) -> str:
    """L'errore in italiano, per chi guarda la pagina: il dettaglio resta nei log."""
    if stato_http == 429:
        return "Quota esaurita (429): la fonte rifiuta altre richieste per ora."
    if stato_http is not None:
        return f"La fonte risponde con un errore del server ({stato_http})."
    if eccezione is not None:
        return f"Fonte non raggiungibile ({type(eccezione).__name__})."
    return "Errore sconosciuto."


def annota(url: str, *, errore: str | None = None, quando: datetime | None = None) -> None:
    fonte = fonte_di(url)
    if fonte is None:
        return
    adesso = quando or datetime.now(UTC)
    esito = _REGISTRO.setdefault(fonte, Esito())
    if errore is None:
        esito.ultimo_ok = adesso
    else:
        esito.ultimo_errore = adesso
        esito.errore = errore


def svuota() -> dict[str, Esito]:
    """Il registro accumulato dall'ultimo riversamento, e un registro vuoto."""
    fuori = dict(_REGISTRO)
    _REGISTRO.clear()
    return fuori
