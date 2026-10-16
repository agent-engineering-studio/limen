"""Registrazione dei sensori dei cittadini, senza login (#253, epic #247).

Chi ha costruito un sensore compila il modulo di ``#/sensori``: tipo,
posizione, la **CSR** del dispositivo, la mail, la licenza dei dati e le
regole di sicurezza. Il modulo non crea un dispositivo: scrive una richiesta e
manda una mail a chi cura il progetto, che la approva dalla CLI
(``limen sensore approva``). Il registro resta una whitelist.

La CSR e non la chiave: il dispositivo genera la sua chiave privata e la
tiene (#252), Limen firma il certificato e lo manda per mail. Un certificato è
pubblico, una chiave in una casella di posta no.

Le difese del modulo sono quelle di :mod:`limen.core.contributi` — campo
nascosto, tempo minimo, limite per indirizzo e complessivo — più la quota di
dispositivi per registrante. La richiesta si scrive nella stessa transazione
in cui parte la mail: se la mail non parte, non resta niente.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from limen.config.settings import SensoriRegistrazioneSettings
from limen.core.contributi import Limitatore, _Email
from limen.core.logging import get_logger
from limen.data.repos import sensori_registrazioni_repo as repo
from limen.integrations.iot.schemas import ID_DISPOSITIVO, ID_RISERVATI

log = get_logger(__name__)

# Niente inclinometri né fessurimetri: senza un geologo una crepa in un muro
# non è un indicatore di frana, e K resta ai dispositivi istituzionali.
TipoSensore = Literal["pluviometro", "umidita_suolo"]

TIPO_IT: dict[str, str] = {
    "pluviometro": "Pluviometro",
    "umidita_suolo": "Umidità del suolo",
}

LICENZA = "CC-BY-4.0"

_PEM_CSR = Annotated[str, StringConstraints(strip_whitespace=True, min_length=100, max_length=4000)]


class CsrNonValidaError(ValueError):
    pass


class RichiestaSensoreIn(BaseModel):
    """Il modulo come arriva dal browser."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoSensore
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    csr: _PEM_CSR
    email: _Email
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    # Base64 di un JPEG o PNG; il tetto vero è in settings, questo ferma un
    # corpo assurdo prima di decodificarlo.
    foto: Annotated[str, StringConstraints(max_length=8_000_000)] | None = None
    licenza: Literal["CC-BY-4.0"]
    regole_sicurezza: Literal[True]
    informativa: Literal[True]
    compilato_in_ms: int = Field(..., ge=0)
    sito_web: str = ""

    @field_validator("email")
    @classmethod
    def _minuscola(cls, v: str) -> str:
        return v.lower()


@dataclass(frozen=True, slots=True)
class Csr:
    device_id: str
    impronta: str


def leggi_csr(pem: str) -> Csr:
    """L'id del dispositivo dalla CSR, dopo averne verificato la firma.

    La firma prova che chi ha mandato la CSR ha la chiave privata. La curva è
    P-256 perché è l'unica del secure element ATECC608 (#252).
    """
    try:
        csr = x509.load_pem_x509_csr(pem.encode())
    except ValueError:
        raise CsrNonValidaError("non è una CSR in formato PEM") from None
    if not csr.is_signature_valid:
        raise CsrNonValidaError("la firma della CSR non è valida")
    chiave = csr.public_key()
    if not isinstance(chiave, ec.EllipticCurvePublicKey) or chiave.curve.name != "secp256r1":
        raise CsrNonValidaError("serve una chiave EC P-256 (prime256v1)")
    cn = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(cn) != 1 or not isinstance(cn[0].value, str):
        raise CsrNonValidaError("la CSR deve avere un solo CN, l'id del dispositivo")
    device_id = cn[0].value
    if not ID_DISPOSITIVO.match(device_id):
        raise CsrNonValidaError(
            "il CN va scritto in minuscole, cifre e trattini, da 3 a 63 caratteri"
        )
    if device_id in ID_RISERVATI:
        raise CsrNonValidaError(f"'{device_id}' è un id riservato")
    h = hashes.Hash(hashes.SHA256())
    h.update(chiave.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo))
    return Csr(device_id=device_id, impronta=h.finalize().hex(":"))


def _foto(b64: str, *, max_kb: int) -> tuple[str, str, bytes]:
    try:
        dati = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("la foto non è in base64") from None
    if len(dati) > max_kb * 1024:
        raise ValueError(f"la foto supera {max_kb} KB")
    if dati.startswith(b"\xff\xd8\xff"):
        return "installazione.jpg", "image/jpeg", dati
    if dati.startswith(b"\x89PNG\r\n\x1a\n"):
        return "installazione.png", "image/png", dati
    raise ValueError("la foto deve essere JPEG o PNG")


class Esito:
    """Come è andato un invio, per l'endpoint."""


@dataclass(frozen=True, slots=True)
class Ricevuta(Esito):
    pass


@dataclass(frozen=True, slots=True)
class Scartata(Esito):
    """Un programma: si risponde come a un invio riuscito."""


@dataclass(frozen=True, slots=True)
class Chiusa(Esito):
    pass


@dataclass(frozen=True, slots=True)
class TroppiInvii(Esito):
    pass


@dataclass(frozen=True, slots=True)
class NonValida(Esito):
    motivo: str


@dataclass(frozen=True, slots=True)
class NonPartita(Esito):
    pass


class _MailNonPartitaError(Exception):
    pass


class _DoppioInvioError(Exception):
    pass


LIMITATORE = Limitatore()


def componi_mail(
    dati: RichiestaSensoreIn, *, richiesta_id: int, csr: Csr, cell_id: str, foto: bool
) -> tuple[str, str]:
    oggetto = f"[Limen] Richiesta sensore #{richiesta_id} · {TIPO_IT[dati.tipo]} · {csr.device_id}"
    righe = [
        f"Richiesta di registrazione #{richiesta_id}",
        "",
        f"Dispositivo: {csr.device_id}",
        f"Tipo: {TIPO_IT[dati.tipo]}",
        f"Posizione proposta: {dati.lat:.5f}, {dati.lon:.5f} (cella {cell_id})",
        f"Impronta della chiave (SHA-256): {csr.impronta}",
        f"Licenza dei dati: {dati.licenza}",
        f"Foto dell'installazione: {'allegata' if foto else 'non inviata'}",
        "",
        "— Note di chi scrive",
        dati.note or "nessuna",
        "",
        "— Per decidere",
        f"  uv run limen sensore approva {richiesta_id}",
        f"  uv run limen sensore respingi {richiesta_id}",
        "",
        "Approvare firma la CSR, crea il dispositivo al livello 0 (fuori dallo",
        "scoring) e manda il certificato al registrante. Per rispondere a chi ha",
        "scritto basta rispondere a questa mail.",
    ]
    return oggetto, "\n".join(righe)


async def ricevi(
    dati: RichiestaSensoreIn,
    *,
    ip: str,
    settings: SensoriRegistrazioneSettings,
    destinatari: list[str],
    invia: Callable[..., Awaitable[bool]],
    limitatore: Limitatore | None = None,
) -> Esito:
    limitatore = limitatore or LIMITATORE
    if not settings.aperta:
        return Chiusa()
    if dati.sito_web:
        log.info("sensori.registrazione.scartata", motivo="campo_nascosto")
        return Scartata()
    if dati.compilato_in_ms < settings.secondi_minimi * 1000:
        log.info("sensori.registrazione.scartata", motivo="troppo_veloce")
        return Scartata()
    if not destinatari:
        log.warning("sensori.registrazione.non_configurata")
        return NonPartita()

    try:
        csr = leggi_csr(dati.csr)
        allegati = [] if dati.foto is None else [_foto(dati.foto, max_kb=settings.max_foto_kb)]
    except ValueError as exc:
        return NonValida(str(exc))
    # Il limite prima di ogni domanda al database: altrimenti il modulo
    # direbbe, senza freno, quali id esistono. Un rifiuto consuma il posto.
    momento = await limitatore.prenota(
        ip, max_per_ip=settings.max_per_ip_ora, max_totali=settings.max_totali_ora
    )
    if momento is None:
        log.warning("sensori.registrazione.limite")
        return TroppiInvii()
    cell_id = await repo.cella_per_punto(dati.lon, dati.lat)
    if cell_id is None:
        return NonValida("la posizione è fuori dal territorio coperto da Limen")
    if await repo.id_in_uso(csr.device_id):
        return NonValida(f"l'id '{csr.device_id}' è già in uso: scegli un altro CN")

    try:
        async with repo.transazione() as conn:
            registrante_id = await repo.registrante_bloccato(conn, dati.email)
            occupati = await repo.posti_occupati(conn, registrante_id)
            if occupati >= settings.max_dispositivi_per_registrante:
                # Senza il conteggio: la mail non è verificata, e il numero
                # direbbe a chiunque quanti sensori ha un indirizzo.
                return NonValida(
                    "questo indirizzo ha raggiunto il numero massimo di dispositivi "
                    f"({settings.max_dispositivi_per_registrante})"
                )
            richiesta_id = await repo.inserisci_richiesta(
                conn,
                registrante_id=registrante_id,
                device_id=csr.device_id,
                device_type=dati.tipo,
                lon=dati.lon,
                lat=dati.lat,
                cell_id=cell_id,
                csr=dati.csr,
                licenza=dati.licenza,
            )
            if richiesta_id is None:
                # Lo stesso id inviato due volte in parallelo: il vincolo del
                # database l'ha fermato, la transazione si annulla.
                raise _DoppioInvioError
            oggetto, testo = componi_mail(
                dati, richiesta_id=richiesta_id, csr=csr, cell_id=cell_id, foto=bool(allegati)
            )
            try:
                partita = await invia(
                    destinatari=destinatari,
                    oggetto=oggetto,
                    testo=testo,
                    rispondi_a=dati.email,
                    allegati=allegati,
                )
            except Exception as exc:  # una mail persa non deve diventare un 500 muto
                log.warning(
                    "sensori.registrazione.mail_errore",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                partita = False
            if not partita:
                # Annulla la transazione: una richiesta che nessuno ha
                # ricevuto occuperebbe un posto della quota per sempre.
                raise _MailNonPartitaError
    except _DoppioInvioError:
        await limitatore.libera(ip, momento)
        return NonValida(f"l'id '{csr.device_id}' è già in uso: scegli un altro CN")
    except _MailNonPartitaError:
        await limitatore.libera(ip, momento)
        log.warning("sensori.registrazione.mail_non_inviata", device_id=csr.device_id)
        return NonPartita()
    log.info("sensori.registrazione.ricevuta", richiesta=richiesta_id, device_id=csr.device_id)
    return Ricevuta()
