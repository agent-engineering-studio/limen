"""Ingestore del protocollo v2 sul broker dei sensori (#252, epic #247).

Si abbona a ``limen/v2/+/obs`` e ``limen/v2/+/status`` sul broker dei sensori
(#260) con il certificato dell'ingestore. L'identità del dispositivo è il
segmento ``{id}`` del topic: l'ACL del broker lascia scrivere su
``limen/v2/%u/…`` soltanto al dispositivo il cui certificato ha quel CN, quindi
qui l'id è già autenticato e nessun campo del payload lo può cambiare.

Ogni messaggio passa, in quest'ordine, da:

1. **dimensione** — oltre ``max_payload_bytes`` si scarta senza leggerlo;
2. **frequenza** — oltre ``max_messaggi_al_minuto`` per dispositivo si
   scarta; troppi scarti in un'ora mettono il dispositivo in quarantena. Viene
   prima del database, così un firmware in loop non lo tocca;
3. **registro** — un id sconosciuto o in quarantena si scarta;
4. **SenML** — vedi :mod:`limen.integrations.iot.senml`;
5. **tempo** — una misura nel futuro oltre la tolleranza, o più vecchia di
   ``max_ritardo_giorni``, fa scartare il messaggio: il dispositivo ha
   l'orologio sbagliato, e nessuna delle sue misure ha un'ora di cui fidarsi;
6. **ritardo** — una misura più vecchia di ``ritardo_minuti`` si salva marcata
   ``in_ritardo``: resta nell'archivio, non entra nel rollup e quindi non
   tocca lo scoring;
7. **calibrazione e QC**, come nel v1, in ordine di tempo e contando anche i
   campioni dello stesso messaggio; per i dati in ritardo il solo controllo
   di intervallo, perché il «campione precedente» di un arretrato non esiste;
8. **sequenza e salvataggio**, in una transazione: la sequenza deve superare
   l'ultima accettata, o il messaggio è un replay e non si scrive niente.

Che una misura salvata conti per lo scoring lo decide poi il livello del
dispositivo (#251), non questo modulo. Gira nel worker, mai nell'API.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import aiomqtt
import structlog

from limen.config.settings import IotSettings
from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import sensor_devices_repo, sensor_observations_repo
from limen.data.repos.sensor_observations_repo import SensorObservation
from limen.integrations.iot.mqtt_ingestor import (
    calibrate,
    qc_in_tempo_reale,
    sigma_overrides_for,
)
from limen.integrations.iot.partitions import ensure_partition_window
from limen.integrations.iot.qc import QcQuality, check_range
from limen.integrations.iot.schemas import CANONICAL_UNITS, Observation, ObservedProperty
from limen.integrations.iot.senml import SenmlError, analizza

_log: structlog.stdlib.BoundLogger = get_logger(__name__)

# Lo stesso formato che la CA accetta come CN (scripts/sensori_ca.sh).
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")
_MINUTO = timedelta(minutes=1)
_ORA = timedelta(hours=1)


class Esito(StrEnum):
    SALVATO = "salvato"
    STATO = "stato"
    TROPPO_GRANDE = "troppo_grande"
    TOPIC = "topic"
    FREQUENZA = "frequenza"
    QUARANTENA = "quarantena"
    SCONOSCIUTO = "sconosciuto"
    MALFORMATO = "malformato"
    FUTURO = "futuro"
    TROPPO_VECCHIO = "troppo_vecchio"
    SEQUENZA = "sequenza"
    ERRORE = "errore"


@dataclass
class _Finestre:
    accettati: deque[datetime] = field(default_factory=deque)
    scarti: deque[datetime] = field(default_factory=deque)


class LimiteFrequenza:
    """Finestra scorrevole per dispositivo, in memoria.

    In memoria basta: l'ingestore gira in un solo processo (il worker ha una
    replica), e dopo un riavvio ricominciare da zero non apre nessun varco che
    il broker non chiuda già.
    """

    def __init__(self, *, al_minuto: int, scarti_per_quarantena: int) -> None:
        self._al_minuto = al_minuto
        self._scarti_per_quarantena = scarti_per_quarantena
        self._per_dispositivo: dict[str, _Finestre] = {}

    def valuta(self, device_id: str, adesso: datetime) -> Esito | None:
        """``None`` se il messaggio passa, altrimenti perché si scarta."""
        f = self._per_dispositivo.setdefault(device_id, _Finestre())
        while f.accettati and adesso - f.accettati[0] >= _MINUTO:
            f.accettati.popleft()
        while f.scarti and adesso - f.scarti[0] >= _ORA:
            f.scarti.popleft()
        if len(f.accettati) < self._al_minuto:
            f.accettati.append(adesso)
            return None
        f.scarti.append(adesso)
        if len(f.scarti) >= self._scarti_per_quarantena:
            f.scarti.clear()
            return Esito.QUARANTENA
        return Esito.FREQUENZA


def _topic(topic: str) -> tuple[str, str] | None:
    parti = topic.split("/")
    if len(parti) != 4 or parti[0] != "limen" or parti[1] != "v2":
        return None
    device_id, tipo = parti[2], parti[3]
    if not _ID.match(device_id) or tipo not in ("obs", "status"):
        return None
    return device_id, tipo


class IngestoreV2:
    """Consumer MQTT del broker dei sensori, una pipeline per messaggio."""

    def __init__(
        self,
        settings: IotSettings,
        *,
        sigma_v: float | None = None,
        adesso: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._c = settings.cittadini
        self._sigma_overrides = sigma_overrides_for(sigma_v)
        self._adesso = adesso
        self._limite = LimiteFrequenza(
            al_minuto=self._c.max_messaggi_al_minuto,
            scarti_per_quarantena=self._c.scarti_per_quarantena,
        )
        self._task: asyncio.Task[None] | None = None
        self._fermo = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("IngestoreV2 già avviato")
        # Il job mensile delle partizioni gira il 2 del mese: un worker che
        # parte dopo mesi di fermo non deve aspettarlo per poter scrivere.
        async with acquire() as conn:
            await ensure_partition_window(
                conn,
                reference=self._adesso().date(),
                window_months=self._settings.partition_window_months,
            )
        self._task = asyncio.create_task(self._run(), name="limen-iot-ingestore-v2")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._fermo.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None

    async def _run(self) -> None:
        tls = aiomqtt.TLSParameters(
            ca_certs=self._c.cafile,
            certfile=self._c.certfile,
            keyfile=self._c.keyfile,
        )
        while not self._fermo.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=self._c.broker_host,
                    port=self._c.broker_port,
                    identifier=self._c.client_id,
                    tls_params=tls,
                ) as client:
                    await client.subscribe("limen/v2/+/obs", qos=1)
                    await client.subscribe("limen/v2/+/status", qos=1)
                    _log.info("iot.v2.connesso", broker=self._c.broker_host)
                    async for message in client.messages:
                        await self.gestisci(
                            topic=str(message.topic), payload=bytes(message.payload)
                        )
            except asyncio.CancelledError:
                raise
            except (aiomqtt.MqttError, OSError, TimeoutError) as exc:
                _log.warning("iot.v2.disconnesso", error=str(exc), error_type=type(exc).__name__)
                await asyncio.sleep(5.0)

    async def gestisci(self, *, topic: str, payload: bytes) -> Esito:
        try:
            esito = await self._gestisci(topic=topic, payload=payload)
        except Exception as exc:
            # Un errore del database su un messaggio non deve fermare il
            # consumer: gli altri dispositivi continuano a essere letti.
            _log.error("iot.v2.errore", topic=topic, error=str(exc), error_type=type(exc).__name__)
            return Esito.ERRORE
        if esito not in (Esito.SALVATO, Esito.STATO):
            _log.info("iot.v2.scartato", topic=topic, esito=esito.value)
        return esito

    async def _gestisci(self, *, topic: str, payload: bytes) -> Esito:
        ricevuto = self._adesso()
        if len(payload) > self._c.max_payload_bytes:
            return Esito.TROPPO_GRANDE
        parsed = _topic(topic)
        if parsed is None:
            return Esito.TOPIC
        device_id, tipo = parsed

        limite = self._limite.valuta(device_id, ricevuto)
        if limite is Esito.QUARANTENA:
            await sensor_devices_repo.set_status(device_id, "quarantined")
            _log.warning("iot.v2.quarantena_per_frequenza", device_id=device_id)
            return limite
        if limite is not None:
            return limite

        device = await sensor_devices_repo.get_device(device_id)
        if device is None:
            return Esito.SCONOSCIUTO
        if device.status == "quarantined":
            return Esito.QUARANTENA

        if tipo == "status":
            stato = payload.strip()
            if stato not in (b"online", b"offline"):
                return Esito.MALFORMATO
            await sensor_devices_repo.stato_dal_dispositivo(
                device_id, "online" if stato == b"online" else "offline"
            )
            return Esito.STATO

        try:
            messaggio = analizza(payload, device_id=device_id, ricevuto=ricevuto)
        except SenmlError as exc:
            _log.info("iot.v2.senml", device_id=device_id, error=str(exc))
            return Esito.MALFORMATO
        if messaggio.ignorate:
            _log.info("iot.v2.grandezze_ignorate", device_id=device_id, nomi=messaggio.ignorate)

        limite_futuro = ricevuto + timedelta(seconds=self._c.tolleranza_futuro_secondi)
        if any(m.istante > limite_futuro for m in messaggio.misure):
            return Esito.FUTURO
        limite_passato = ricevuto - timedelta(days=self._c.max_ritardo_giorni)
        if any(m.istante < limite_passato for m in messaggio.misure):
            return Esito.TROPPO_VECCHIO
        ritardo = timedelta(minutes=self._c.ritardo_minuti)
        righe: list[SensorObservation] = []
        valutate: dict[ObservedProperty, list[tuple[datetime, float]]] = {}
        for m in sorted(messaggio.misure, key=lambda m: m.istante):
            grezza = Observation(
                contract_version="v2",
                thing_id=device_id,
                observed_property=m.grandezza,
                phenomenon_time=m.istante,
                result_value=m.valore,
                result_unit=m.unita,
            )
            canonica = grezza.model_copy(
                update={
                    "result_value": calibrate(grezza, device.calibration),
                    "result_unit": CANONICAL_UNITS[m.grandezza],
                }
            )
            in_ritardo = ricevuto - m.istante > ritardo
            qualita: QcQuality = (
                check_range(canonica, self._settings)
                if in_ritardo
                else await qc_in_tempo_reale(
                    canonica,
                    settings=self._settings,
                    sigma_overrides=self._sigma_overrides,
                    nel_messaggio=valutate.get(m.grandezza, []),
                )
            )
            if not in_ritardo:
                valutate.setdefault(m.grandezza, []).append((m.istante, canonica.result_value))
            righe.append(
                SensorObservation(
                    device_id=device_id,
                    observed_property=m.grandezza,
                    phenomenon_time=m.istante,
                    result_value=canonica.result_value,
                    result_unit=canonica.result_unit,
                    raw_value=m.valore,
                    quality=qualita,
                    sequenza=messaggio.sequenza,
                    in_ritardo=in_ritardo,
                )
            )

        if not await sensor_observations_repo.salva_messaggio(device_id, messaggio.sequenza, righe):
            return Esito.SEQUENZA
        if righe:
            await sensor_devices_repo.touch_last_seen(
                device_id, at=max(r.phenomenon_time for r in righe)
            )
        return Esito.SALVATO


__all__ = ["Esito", "IngestoreV2", "LimiteFrequenza"]
