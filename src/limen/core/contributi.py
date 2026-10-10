"""I contributi degli esperti: dall'ispettore della cella a chi cura il progetto.

Un geologo che non scrive codice non deve passare da GitHub. Compila un
modulo sotto la cella che sta guardando e parte una mail, con i numeri di
quel momento, a cui chi cura il progetto può rispondere direttamente.
**Limen non salva niente**: né il contributo né i dati di chi scrive, che
esistono solo nella mail. Per questo la mail parte prima della risposta —
se non parte, chi ha scritto lo sa e può riprovare, invece di credere
arrivato un messaggio perso. Nessun contributo tocca i numeri.

Il modulo è pubblico, quindi le difese sono qui e non nel browser: un campo
nascosto che solo i programmi compilano, un tempo minimo di compilazione, un
limite per indirizzo e uno complessivo, tenuti in memoria. Ai primi due si
risponde come se fosse andato tutto bene — dire a un programma perché è
stato scartato gli insegna a non esserlo.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from limen.config.settings import ContributiSettings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.data.repos import contributi_repo

log = get_logger(__name__)

TipoContributo = Literal["frana_non_censita", "valutazione", "pesi_soglie", "mitigazione", "altro"]

TIPO_IT: dict[str, str] = {
    "frana_non_censita": "Frana non censita",
    "valutazione": "La valutazione non torna",
    "pesi_soglie": "Peso o soglia da rivedere",
    "mitigazione": "Opera di mitigazione presente",
    "altro": "Altro",
}

_Testo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=4000)]
_Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
_Breve = Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]
# Niente spazi né a capo: l'indirizzo finisce nell'intestazione Reply-To, e un
# a capo lì dentro aggiungerebbe intestazioni a piacere di chi scrive.
_Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=254,
        pattern=r"^[^@\s<>,;\"]+@[^@\s<>,;\"]+\.[^@\s<>,;\"]{2,}$",
    ),
]


class ContributoIn(BaseModel):
    """Il modulo come arriva dal browser."""

    model_config = ConfigDict(extra="forbid")

    cell_id: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    hazard: HazardType | None = None
    tipo: TipoContributo
    testo: _Testo
    fonte_url: HttpUrl | None = None
    nome: _Nome | None = None
    email: _Email
    affiliazione: _Breve | None = None
    linkedin_url: HttpUrl | None = None
    consenso: Literal[True]
    compilato_in_ms: int = Field(..., ge=0)
    # Il campo che una persona non vede e un programma riempie.
    sito_web: str = ""

    @model_validator(mode="after")
    def _chi_scrive(self) -> ContributoIn:
        # Nome e cognome, o in alternativa il profilo LinkedIn: chi cura il
        # progetto deve poter sapere con chi parla, non per forza dai due.
        if self.nome is None and self.linkedin_url is None:
            raise ValueError("serve il nome e cognome oppure il profilo LinkedIn")
        return self


class Esito:
    """Come è andato un invio, per l'endpoint."""


@dataclass(frozen=True, slots=True)
class Inviato(Esito):
    pass


@dataclass(frozen=True, slots=True)
class Scartato(Esito):
    """Un programma, non una persona: si risponde come a un invio riuscito."""


@dataclass(frozen=True, slots=True)
class TroppiInvii(Esito):
    pass


@dataclass(frozen=True, slots=True)
class NonPartito(Esito):
    """La mail non è partita, o il servizio non è configurato: niente è salvato."""


class CellaSconosciutaError(ValueError):
    pass


@dataclass
class Limitatore:
    """Invii dell'ultima ora per indirizzo e in tutto, solo in memoria.

    Un solo processo API serve il modulo, quindi un lock basta a rendere
    atomici controllo e prenotazione: due invii in parallelo non passano
    entrambi l'ultimo posto libero. L'indirizzo non esce da qui e sparisce
    con la sua finestra; a ogni riavvio il conteggio riparte, che per un
    limite orario va bene.
    """

    finestra_s: float = 3600.0
    _per_ip: dict[str, deque[float]] = field(default_factory=dict)
    _tutti: deque[float] = field(default_factory=deque)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _pulisci(self, ora: float) -> None:
        soglia = ora - self.finestra_s
        while self._tutti and self._tutti[0] <= soglia:
            self._tutti.popleft()
        for ip in list(self._per_ip):
            coda = self._per_ip[ip]
            while coda and coda[0] <= soglia:
                coda.popleft()
            if not coda:
                del self._per_ip[ip]

    async def prenota(self, ip: str, *, max_per_ip: int, max_totali: int) -> float | None:
        """Il momento prenotato, o ``None`` se un limite è già pieno."""
        async with self._lock:
            ora = time.monotonic()
            self._pulisci(ora)
            coda = self._per_ip.setdefault(ip, deque())
            if len(coda) >= max_per_ip or len(self._tutti) >= max_totali:
                return None
            coda.append(ora)
            self._tutti.append(ora)
            return ora

    async def libera(self, ip: str, momento: float) -> None:
        """Restituisce il posto di un invio che non è partito."""
        async with self._lock:
            coda = self._per_ip.get(ip)
            if coda and momento in coda:
                coda.remove(momento)
            if momento in self._tutti:
                self._tutti.remove(momento)


LIMITATORE = Limitatore()


def _numero(v: Any) -> str:
    return f"{v:.2f}" if isinstance(v, int | float) else "n.d."


def componi_mail(
    dati: ContributoIn, stato: dict[str, Any], *, map_base_url: str
) -> tuple[str, str]:
    """Oggetto e testo della mail: tutto quello che serve per valutarlo senza aprire altro."""
    oggetto = f"[Limen] Contributo esperto · {TIPO_IT[dati.tipo]} · {dati.cell_id}"
    # La SPA legge la rotta dall'hash: un link in query aprirebbe la home.
    cella = {"cella": dati.cell_id, "lon": f"{stato['lon']:.5f}", "lat": f"{stato['lat']:.5f}"}
    link = f"{map_base_url.rstrip('/')}/#/dashboard?{urlencode(cella)}"
    righe = [
        f"Contributo — {TIPO_IT[dati.tipo]}",
        "",
        dati.testo,
        "",
        f"Fonte: {dati.fonte_url}" if dati.fonte_url else "Fonte: non indicata",
        "",
        "— Chi scrive",
        f"Nome: {dati.nome or 'non indicato'}",
        f"Email: {dati.email}",
    ]
    if dati.affiliazione:
        righe.append(f"Dipartimento o ente: {dati.affiliazione}")
    if dati.linkedin_url:
        righe.append(f"LinkedIn: {dati.linkedin_url}")
    righe += [
        "",
        "— La cella, come la vedeva",
        f"Cella: {dati.cell_id} · regione {stato['aoi_id']}",
        f"Coordinate: {stato['lat']:.5f}, {stato['lon']:.5f}",
        f"Mappa: {link}",
    ]
    if dati.hazard is not None:
        righe.append(f"Pericolo che stava guardando: {dati.hazard.value}")
    for p in stato["pericoli"]:
        righe.append(
            f"  · {p['hazard']}: {_numero(p['score'])} ({p['classe'] or 'n.d.'}),"
            f" calcolato {p['calcolato']}"
        )
        fattori = p.get("fattori") or {}
        for nome, valore in fattori.items():
            if isinstance(valore, int | float) and not isinstance(valore, bool):
                righe.append(f"      {nome} = {_numero(valore)}")
    righe += [
        "",
        "Per rispondere a chi ha scritto basta rispondere a questa mail.",
    ]
    return oggetto, "\n".join(righe)


async def ricevi(
    dati: ContributoIn,
    *,
    ip: str,
    settings: ContributiSettings,
    map_base_url: str,
    invia: Callable[..., Awaitable[bool]],
    limitatore: Limitatore | None = None,
) -> Esito:
    limitatore = limitatore or LIMITATORE
    if dati.sito_web:
        log.info("contributi.scartato", motivo="campo_nascosto")
        return Scartato()
    if dati.compilato_in_ms < settings.secondi_minimi * 1000:
        log.info("contributi.scartato", motivo="troppo_veloce", ms=dati.compilato_in_ms)
        return Scartato()
    if not settings.destinatari:
        log.warning("contributi.non_configurati")
        return NonPartito()

    stato = await contributi_repo.stato_cella(dati.cell_id)
    if stato is None:
        raise CellaSconosciutaError(dati.cell_id)

    momento = await limitatore.prenota(
        ip, max_per_ip=settings.max_per_ip_ora, max_totali=settings.max_totali_ora
    )
    if momento is None:
        log.warning("contributi.limite")
        return TroppiInvii()

    oggetto, testo = componi_mail(dati, stato, map_base_url=map_base_url)
    try:
        partita = await invia(
            destinatari=settings.destinatari,
            oggetto=oggetto,
            testo=testo,
            rispondi_a=dati.email,
        )
    except Exception as exc:  # una mail persa non deve diventare un 500 muto
        log.warning("contributi.mail_errore", error=str(exc), error_type=type(exc).__name__)
        partita = False
    if not partita:
        await limitatore.libera(ip, momento)
        log.warning("contributi.mail_non_inviata", tipo=dati.tipo, cell_id=dati.cell_id)
        return NonPartito()
    log.info("contributi.inviato", tipo=dati.tipo, cell_id=dati.cell_id)
    return Inviato()
