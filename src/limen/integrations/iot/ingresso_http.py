"""Ingresso HTTP firmato del protocollo v2 (#265, epic #247).

Per un dispositivo che non può tenere una sessione MQTT su TLS: un modem
LTE-M che si sveglia una volta l'ora, un datalogger che sa solo fare un POST.
Consegna lo stesso SenML dell'MQTT a

    POST /sensori/v2/{id}/obs
    X-Limen-Tempo: <secondi Unix dell'invio>
    X-Limen-Firma: <firma in base64>

e la firma (vedi :mod:`limen.integrations.iot.firma_http`) prende il posto del
certificato: l'MQTT autentica l'id con l'ACL del broker, qui lo autentica la
chiave registrata. Firma, chiave o tempo sbagliati ⇒ 401 e nulla si salva.
Ogni messaggio firmato passa dalla pipeline una volta sola: rimandato uguale
riceve l'esito del primo invio, e un nuovo tentativo si rifirma con un tempo
nuovo.
Dopo la firma il messaggio è esattamente un messaggio MQTT sul topic
``limen/v2/{id}/obs``: stessa pipeline, stesso limite di frequenza, stessa
sequenza, e quindi le stesse righe.

Sullo stesso listener arriva il webhook di The Things Network (#266):

    POST /sensori/v2/ttn
    Authorization: Bearer <segreto dell'applicazione TTN>

con l'``uplink_message`` di TTN v3. Il segreto è dell'applicazione e vale solo
per i dispositivi registrati con quell'applicazione; il dispositivo è il
DevEUI. Il ``frm_payload`` è SenML CBOR, riscritto in JSON e poi trattato come
sopra. La ``seq`` è quella di SenML, non il frame counter LoRaWAN, che si
azzera a ogni join.

Gira nel worker accanto all'ingestore MQTT, mai nell'API pubblica: nginx lo
raggiunge con una ``location`` dedicata e il suo ``limit_req``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hashlib
import hmac
import json
import re
import socket
from collections import deque
from collections.abc import Awaitable, Callable, Generator
from datetime import datetime
from http import HTTPStatus
from typing import Any

import structlog
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from limen.config.settings import IotCittadiniSettings
from limen.core.logging import get_logger
from limen.data.repos import sensor_devices_repo
from limen.integrations.iot.firma_http import messaggio_firmato, verifica
from limen.integrations.iot.schemas import ID_DISPOSITIVO
from limen.integrations.iot.senml import SenmlError, cbor_a_json

_log: structlog.stdlib.BoundLogger = get_logger(__name__)

Gestisci = Callable[..., Awaitable[str]]

# L'esito della pipeline come risposta HTTP. Un doppione (sequenza già vista)
# è 409: il dispositivo che ha perso la risposta al primo invio sa che quel
# messaggio c'è già e passa al successivo.
_STATO_PER_ESITO: dict[str, HTTPStatus] = {
    "salvato": HTTPStatus.OK,
    "sequenza": HTTPStatus.CONFLICT,
    "frequenza": HTTPStatus.TOO_MANY_REQUESTS,
    "quarantena": HTTPStatus.FORBIDDEN,
    "sconosciuto": HTTPStatus.UNAUTHORIZED,
    "troppo_grande": HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    "malformato": HTTPStatus.BAD_REQUEST,
    "topic": HTTPStatus.BAD_REQUEST,
    "futuro": HTTPStatus.UNPROCESSABLE_ENTITY,
    "troppo_vecchio": HTTPStatus.UNPROCESSABLE_ENTITY,
}


def _risposta(stato: HTTPStatus, esito: str) -> JSONResponse:
    return JSONResponse({"esito": esito}, status_code=stato)


async def _corpo(request: Request, massimo: int) -> bytes | None:
    """Il corpo, o ``None`` appena supera ``massimo``: non si legge oltre."""
    corpo = bytearray()
    async for pezzo in request.stream():
        corpo.extend(pezzo)
        if len(corpo) > massimo:
            return None
    return bytes(corpo)


# Quanto a lungo una chiave letta dal registro vale senza rileggerla. Una
# chiave pubblica cambia solo all'approvazione: un dispositivo appena approvato aspetta
# al più questo, e una raffica di firme false non tocca il database (che
# l'ingestore divide con l'MQTT, su un pool di quattro connessioni).
_CHIAVE_VALE_SECONDI = 60.0
# Un tempo nella firma con più cifre di così non è un orario: è un header
# costruito per far saltare la conversione.
_CIFRE_TEMPO = 12


class _Scadenze:
    """Chiavi con una scadenza, in ordine d'inserimento: le scadute si tolgono
    dalla testa. La durata è fissa, quindi l'ordine d'inserimento è anche
    quello di scadenza."""

    def __init__(self) -> None:
        self._ordine: deque[tuple[float, object]] = deque()
        self._valori: dict[object, tuple[float, object]] = {}

    def pulisci(self, adesso: float) -> None:
        while self._ordine and self._ordine[0][0] <= adesso:
            scadenza, chiave = self._ordine.popleft()
            if self._valori.get(chiave, (None,))[0] == scadenza:
                del self._valori[chiave]

    def get(self, chiave: object, adesso: float) -> tuple[bool, object]:
        self.pulisci(adesso)
        trovato = self._valori.get(chiave)
        return (False, None) if trovato is None else (True, trovato[1])

    def metti(self, chiave: object, valore: object, scadenza: float) -> None:
        self._ordine.append((scadenza, chiave))
        self._valori[chiave] = (scadenza, valore)


def applicazione(
    gestisci: Gestisci, c: IotCittadiniSettings, *, adesso: Callable[[], datetime]
) -> Starlette:
    chiavi = _Scadenze()
    # I messaggi firmati già entrati, con il loro esito: ognuno passa una volta
    # sola dalla pipeline. Senza, un
    # POST intercettato e rimandato dentro la finestra consumerebbe la quota al
    # minuto del dispositivo vero fino a metterlo in quarantena, perché la
    # frequenza si conta prima della sequenza. L'impronta è del messaggio e non
    # della firma: ECDSA ha più codifiche valide della stessa firma.
    visti = _Scadenze()

    async def chiave_di(device_id: str, ora: float) -> bytes | None:
        trovata, chiave = chiavi.get(device_id, ora)
        if not trovata:
            chiave = await sensor_devices_repo.chiave_pubblica(device_id)
            chiavi.metti(device_id, chiave, ora + _CHIAVE_VALE_SECONDI)
        return chiave if isinstance(chiave, bytes) else None

    async def ricevi(request: Request) -> Response:
        device_id = request.path_params["device_id"]
        if not ID_DISPOSITIVO.match(device_id):
            return _risposta(HTTPStatus.NOT_FOUND, "topic")
        dichiarata = request.headers.get("content-length", "")
        if dichiarata.isascii() and dichiarata.isdigit() and int(dichiarata) > c.max_payload_bytes:
            return _risposta(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "troppo_grande")
        corpo = await _corpo(request, c.max_payload_bytes)
        if corpo is None:
            return _risposta(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "troppo_grande")

        ora = adesso().timestamp()
        tempo = _tempo(request, ora, c)
        if isinstance(tempo, str):
            return _non_autentico(device_id, tempo)
        try:
            firma = base64.b64decode(request.headers.get("x-limen-firma", ""), validate=True)
        except (binascii.Error, ValueError):
            return _non_autentico(device_id, "firma_illeggibile")
        chiave = await chiave_di(device_id, ora)
        if chiave is None:
            return _non_autentico(device_id, "chiave_sconosciuta")
        messaggio = messaggio_firmato(device_id, tempo, corpo)
        if not verifica(chiave, firma, messaggio):
            return _non_autentico(device_id, "firma")

        impronta = hashlib.sha256(messaggio).digest()
        trovato, primo = visti.get(impronta, ora)
        if trovato and isinstance(primo, asyncio.Future):
            # Lo stesso esito del primo invio, senza ripassare dalla pipeline:
            # un 409 qui direbbe «salvato» anche a un messaggio che ha preso un
            # 429 o un 503 e non è mai entrato (Codex, #298).
            _log.info("iot.http.ripetuto", device_id=device_id)
            esito = str(await asyncio.shield(primo))
        else:
            # Il tempo resta valido fino a `tempo + finestra`, e `tempo` arriva
            # al più a `ora + tolleranza`: fino ad allora va ricordato.
            futuro: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            visti.metti(
                impronta, futuro, ora + c.finestra_firma_secondi + c.tolleranza_futuro_secondi
            )
            esito = "errore"
            try:
                esito = str(
                    await gestisci(
                        topic=f"limen/v2/{device_id}/obs", payload=corpo, dal_broker=False
                    )
                )
            finally:
                futuro.set_result(esito)
        return _risposta(_STATO_PER_ESITO.get(esito, HTTPStatus.SERVICE_UNAVAILABLE), esito)

    segreti = _SegretiTtn()

    async def ttn(request: Request) -> Response:
        dichiarata = request.headers.get("content-length", "")
        if (
            dichiarata.isascii()
            and dichiarata.isdigit()
            and int(dichiarata) > c.ttn_max_corpo_bytes
        ):
            return _risposta(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "troppo_grande")
        corpo = await _corpo(request, c.ttn_max_corpo_bytes)
        if corpo is None:
            return _risposta(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "troppo_grande")
        evento = _evento_ttn(corpo)
        if evento is None:
            return _risposta(HTTPStatus.BAD_REQUEST, "malformato")
        applicazione, dev_eui, uplink = evento

        atteso = await segreti.di(applicazione, adesso().timestamp())
        dato = _bearer(request)
        if (
            atteso is None
            or dato is None
            or not hmac.compare_digest(hashlib.sha256(dato).digest(), atteso)
        ):
            _log.info("iot.ttn.non_autentico", applicazione=applicazione)
            return _risposta(HTTPStatus.UNAUTHORIZED, "segreto")

        # Da qui in poi ogni risposta è 2xx, tranne un nostro errore: il
        # dispositivo non legge la risposta, e TTN mette in pausa un webhook
        # che fallisce — anche per gli altri dispositivi dell'applicazione.
        if uplink is None or dev_eui is None:
            return _risposta(HTTPStatus.ACCEPTED, "ignorato")
        dispositivo = await sensor_devices_repo.per_dev_eui(dev_eui)
        if dispositivo is None or dispositivo[1] != applicazione:
            _log.info("iot.ttn.dev_eui_sconosciuto", applicazione=applicazione, dev_eui=dev_eui)
            return _risposta(HTTPStatus.ACCEPTED, "sconosciuto")
        device_id = dispositivo[0]
        try:
            grezzo = base64.b64decode(str(uplink.get("frm_payload", "")), validate=True)
            if not grezzo or len(grezzo) > c.max_payload_bytes:
                raise SenmlError("frm_payload vuoto o troppo grande")
            payload = cbor_a_json(grezzo)
        except (binascii.Error, ValueError) as exc:  # SenmlError è un ValueError
            _log.info("iot.ttn.senml", device_id=device_id, error=str(exc))
            return _risposta(HTTPStatus.ACCEPTED, "malformato")
        esito = str(
            await gestisci(topic=f"limen/v2/{device_id}/obs", payload=payload, dal_broker=False)
        )
        if esito not in _STATO_PER_ESITO:
            return _risposta(HTTPStatus.SERVICE_UNAVAILABLE, esito)
        return _risposta(HTTPStatus.OK if esito == "salvato" else HTTPStatus.ACCEPTED, esito)

    return Starlette(
        routes=[
            Route("/sensori/v2/ttn", ttn, methods=["POST"]),
            Route("/sensori/v2/{device_id}/obs", ricevi, methods=["POST"]),
        ]
    )


_APPLICAZIONE_TTN = re.compile(r"^[a-z0-9](-?[a-z0-9])*$")
_DEV_EUI = re.compile(r"^[0-9A-Fa-f]{16}$")


# Quanto vale la copia in memoria dei segreti TTN. Una rotazione
# (`limen sensore ttn-segreto`) arriva al webhook entro questo tempo.
_SEGRETI_VALGONO_SECONDI = 5.0


class _SegretiTtn:
    """Tutta `sensori_ttn` in memoria, riletta al più ogni pochi secondi: una
    riga per registrante. Un'applicazione che non esiste, scritta in un corpo
    non autenticato, non costa una query sul pool che l'ingestore divide con
    l'MQTT."""

    def __init__(self) -> None:
        self._segreti: dict[str, bytes] = {}
        self._letti_alle: float | None = None
        self._lucchetto = asyncio.Lock()

    async def di(self, applicazione: str, ora: float) -> bytes | None:
        async with self._lucchetto:
            if self._letti_alle is None or ora - self._letti_alle >= _SEGRETI_VALGONO_SECONDI:
                self._segreti = await sensor_devices_repo.segreti_ttn()
                self._letti_alle = ora
        return self._segreti.get(applicazione)


def _evento_ttn(corpo: bytes) -> tuple[str, str | None, dict[str, Any] | None] | None:
    """Applicazione, DevEUI (maiuscolo) e ``uplink_message`` di un evento TTN v3;
    ``None`` se non si legge l'applicazione. Un DevEUI che manca o è storto
    si scopre dopo il segreto: un evento autenticato riceve sempre un 2xx."""
    try:
        evento = json.loads(corpo)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    if not isinstance(evento, dict):
        return None
    ids = evento.get("end_device_ids")
    if not isinstance(ids, dict) or not isinstance(ids.get("application_ids"), dict):
        return None
    applicazione = ids["application_ids"].get("application_id")
    if not (
        isinstance(applicazione, str)
        and len(applicazione) <= 36
        and _APPLICAZIONE_TTN.fullmatch(applicazione)
    ):
        return None
    dev_eui = ids.get("dev_eui")
    valido = isinstance(dev_eui, str) and _DEV_EUI.fullmatch(dev_eui)
    uplink = evento.get("uplink_message")
    return (
        applicazione,
        dev_eui.upper() if valido and isinstance(dev_eui, str) else None,
        uplink if isinstance(uplink, dict) else None,
    )


def _bearer(request: Request) -> bytes | None:
    schema, _, segreto = request.headers.get("authorization", "").partition(" ")
    if schema.lower() != "bearer" or not segreto.strip():
        return None
    return segreto.strip().encode()


def _tempo(request: Request, ora: float, c: IotCittadiniSettings) -> int | str:
    """Il tempo della firma, o perché non vale. Verso il futuro vale solo la
    tolleranza dell'orologio: una firma datata avanti resterebbe buona più a
    lungo della finestra."""
    testo = request.headers.get("x-limen-tempo", "")
    if not (testo.isascii() and testo.isdigit() and len(testo) <= _CIFRE_TEMPO):
        return "tempo"
    tempo = int(testo)
    if tempo < ora - c.finestra_firma_secondi or tempo > ora + c.tolleranza_futuro_secondi:
        return "fuori_finestra"
    return tempo


def _non_autentico(device_id: str, motivo: str) -> JSONResponse:
    _log.info("iot.http.non_autentico", device_id=device_id, motivo=motivo)
    return _risposta(HTTPStatus.UNAUTHORIZED, "firma")


class _Server(uvicorn.Server):
    # SIGTERM e SIGINT sono del worker, che ferma tutto in ordine: uvicorn non
    # deve sostituire i suoi gestori.
    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        yield


async def servi(
    gestisci: Gestisci, c: IotCittadiniSettings, *, adesso: Callable[[], datetime]
) -> None:
    """Il listener, finché non lo si cancella. Non solleva mai: gira nello
    stesso gruppo dell'ingestore MQTT, e un suo errore lo cancellerebbe."""
    try:
        await _servi(gestisci, c, adesso=adesso)
    except Exception as exc:
        _log.error("iot.http.fermo", error=str(exc), error_type=type(exc).__name__)


async def _servi(
    gestisci: Gestisci, c: IotCittadiniSettings, *, adesso: Callable[[], datetime]
) -> None:
    try:
        presa = socket.create_server((c.http_host, c.http_porta))
    except OSError as exc:
        _log.error("iot.http.porta_non_disponibile", porta=c.http_porta, error=str(exc))
        return
    config = uvicorn.Config(
        applicazione(gestisci, c, adesso=adesso),
        log_config=None,
        access_log=False,
        lifespan="off",
        ws="none",
        server_header=False,
    )
    server = _Server(config)
    _log.info("iot.http.in_ascolto", host=c.http_host, porta=c.http_porta)
    try:
        await server.serve(sockets=[presa])
    finally:
        # Cancellato, uvicorn non arriva al suo shutdown: il server asyncio
        # resterebbe registrato sul descrittore che si sta per chiudere.
        for aperto in server.servers:
            aperto.close()
        presa.close()


__all__ = ["applicazione", "servi"]
