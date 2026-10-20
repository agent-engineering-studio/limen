"""``limen sensore …`` — l'operatore decide sulle richieste dei sensori (#253).

    limen sensore richieste                       le richieste in attesa
    limen sensore approva <richiesta>             firma la CSR, crea il dispositivo, manda il cert
    limen sensore respingi <richiesta>
    limen sensore revoca <id>                     revoca il certificato e mette in quarantena
    limen sensore quarantena <id>
    limen sensore quarantena --registrante <mail> tutti i dispositivi di un registrante
    limen sensore cancella-registrante <mail>     GDPR: revoca, quarantena, cancella la mail

Gira **sull'host**, dalla radice del repo: firmare e revocare passano da
``scripts/sensori_ca.sh``, perché la chiave della CA vive in
``$LIMEN_SENSORI_DIR/ca`` e non entra in nessun container.

Tutti idempotenti: ``approva`` su una richiesta già approvata rimanda la
mail con lo stesso certificato invece di firmarne un altro; revocare,
mettere in quarantena o cancellare due volte non cambia niente.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.core.sensori_registrazione import TIPO_IT, leggi_csr
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import sensor_devices_repo
from limen.data.repos import sensori_registrazioni_repo as repo
from limen.notifications.email import invia_testo

log = get_logger(__name__)


class CaError(RuntimeError):
    pass


class CaSensori:
    """``scripts/sensori_ca.sh``, l'unico che tocca la chiave della CA."""

    def __init__(self, script: str) -> None:
        self.script = script

    async def _esegui(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            self.script,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise CaError(err.decode(errors="replace").strip() or f"exit {proc.returncode}")
        return out.decode()

    async def firma(self, csr: str, *, giorni: int) -> str:
        with tempfile.TemporaryDirectory() as d:
            percorso = Path(d) / "richiesta.csr"
            percorso.write_text(csr)
            return await self._esegui("firma", str(percorso), str(giorni))

    async def revoca(self, device_id: str) -> None:
        await self._esegui("revoca", device_id)

    async def certificato_ca(self) -> str:
        return await self._esegui("ca")


def mail_approvazione(device_id: str, tipo: str, *, broker: str) -> tuple[str, str]:
    oggetto = f"[Limen] Il tuo sensore {device_id} è registrato"
    testo = "\n".join(
        [
            f"Il sensore {device_id} ({TIPO_IT.get(tipo, tipo)}) è nel registro di Limen.",
            "",
            "In allegato:",
            f"  {device_id}.crt  il certificato del dispositivo, firmato dalla CA dei sensori",
            "  ca.crt           la CA, per verificare il broker",
            "",
            "La chiave privata è quella con cui hai generato la CSR: resta sul",
            "dispositivo e non va mandata a nessuno, nemmeno a noi.",
            "",
            f"Broker: {broker} (MQTT su TLS, certificato client obbligatorio)",
            f"Pubblica le misure su limen/v2/{device_id}/obs e lo stato su",
            f"limen/v2/{device_id}/status: il protocollo è nella pagina Sensori di Limen.",
            "",
            "Il sensore parte come osservatore (livello 0): le sue misure si salvano",
            "e si confrontano con il radar, ma non cambiano i punteggi né le allerte.",
            "",
            "Per cancellare la registrazione e i tuoi dati basta rispondere a questa mail.",
        ]
    )
    return oggetto, testo


async def approva(richiesta_id: int, *, settings: Settings, ca: CaSensori) -> int:
    r = await repo.richiesta(richiesta_id)
    if r is None:
        log.error("sensore.richiesta_sconosciuta", richiesta=richiesta_id)
        return 1
    if r.stato == "respinta":
        log.error("sensore.richiesta_respinta", richiesta=richiesta_id)
        return 1
    certificato = r.certificato
    if r.stato == "in_attesa":
        if await sensor_devices_repo.get_device(r.device_id) is not None:
            log.error("sensore.id_in_uso", device_id=r.device_id)
            return 1
        cell_id = r.cell_id or await repo.cella_per_punto(r.lon, r.lat)
        if cell_id is None:
            log.error("sensore.fuori_griglia", richiesta=r.id, lon=r.lon, lat=r.lat)
            return 1
        if certificato is None:
            certificato = await ca.firma(
                r.csr, giorni=settings.iot.cittadini.registrazione.giorni_certificato
            )
            await repo.salva_certificato(r.id, certificato)
        if not await repo.approva(
            r, cell_id=cell_id, certificato=certificato, chiave=leggi_csr(r.csr).chiave
        ):
            log.error("sensore.gia_decisa", richiesta=r.id)
            return 1
        log.info("sensore.approvato", richiesta=r.id, device_id=r.device_id, cell_id=cell_id)
    else:
        dispositivo = await sensor_devices_repo.get_device(r.device_id)
        if dispositivo is not None and dispositivo.status == "quarantined":
            # Un certificato revocato non si rimanda come «registrato».
            log.error("sensore.in_quarantena", device_id=r.device_id)
            return 1
        if dispositivo is not None and await repo.chiave_se_manca(
            r.device_id, leggi_csr(r.csr).chiave
        ):
            log.info("sensore.chiave_aggiunta", device_id=r.device_id)
    assert certificato is not None  # una richiesta approvata ha il suo certificato

    oggetto, testo = mail_approvazione(
        r.device_id, r.device_type, broker=settings.iot.cittadini.registrazione.broker_pubblico
    )
    partita = await invia_testo(
        settings.notifications.email,
        destinatari=[r.email],
        oggetto=oggetto,
        testo=testo,
        allegati=[
            (f"{r.device_id}.crt", "application/x-pem-file", certificato.encode()),
            ("ca.crt", "application/x-pem-file", (await ca.certificato_ca()).encode()),
        ],
    )
    if not partita:
        log.error(
            "sensore.mail_non_partita",
            device_id=r.device_id,
            rimedio=f"rilancia `limen sensore approva {r.id}` per rimandarla",
        )
        return 1
    log.info("sensore.certificato_inviato", device_id=r.device_id)
    return 0


async def respingi(richiesta_id: int) -> int:
    if await repo.respingi(richiesta_id):
        log.info("sensore.respinta", richiesta=richiesta_id)
        return 0
    r = await repo.richiesta(richiesta_id)
    if r is not None and r.stato == "respinta":
        log.info("sensore.gia_respinta", richiesta=richiesta_id)
        return 0
    log.error("sensore.non_respingibile", richiesta=richiesta_id, stato=r and r.stato)
    return 1


async def revoca(device_id: str, *, ca: CaSensori) -> int:
    if await sensor_devices_repo.get_device(device_id) is None:
        log.error("sensore.sconosciuto", device_id=device_id)
        return 1
    # Prima il broker, che è dove il dispositivo smette davvero di parlare.
    await ca.revoca(device_id)
    await sensor_devices_repo.set_status(device_id, "quarantined")
    log.info("sensore.revocato", device_id=device_id)
    return 0


async def quarantena(device_id: str | None, *, registrante: str | None) -> int:
    if registrante is not None:
        rid = await repo.registrante_id(registrante.lower())
        if rid is None:
            log.error("sensore.registrante_sconosciuto")
            return 1
        ids = await repo.dispositivi_del_registrante(rid)
    else:
        assert device_id is not None
        if await sensor_devices_repo.get_device(device_id) is None:
            log.error("sensore.sconosciuto", device_id=device_id)
            return 1
        ids = [device_id]
    for i in ids:
        await sensor_devices_repo.set_status(i, "quarantined")
    log.info("sensore.quarantena", dispositivi=ids)
    return 0


async def cancella_registrante(email: str, *, ca: CaSensori) -> int:
    rid = await repo.registrante_id(email.lower())
    if rid is None:
        log.info("sensore.registrante_assente")
        return 0
    ids = await repo.dispositivi_del_registrante(rid)
    for i in ids:
        await ca.revoca(i)
        await sensor_devices_repo.set_status(i, "quarantined")
    await repo.cancella_registrante(rid)
    log.info("sensore.registrante_cancellato", dispositivi=ids)
    return 0


async def richieste() -> int:
    elenco = await repo.in_attesa()
    for r in elenco:
        log.info(
            "sensore.in_attesa",
            richiesta=r.id,
            device_id=r.device_id,
            tipo=r.device_type,
            cell_id=r.cell_id,
            email=r.email,
            creata=r.creata_at.isoformat(timespec="minutes"),
        )
    log.info("sensore.richieste", in_attesa=len(elenco))
    return 0


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = top.add_parser("sensore", help="registro dei sensori dei cittadini: approva, revoca (#253)")
    sub = p.add_subparsers(dest="sensore_command", required=True)
    sub.add_parser("richieste", help="le richieste in attesa")
    sub.add_parser("approva", help="firma la CSR e crea il dispositivo").add_argument(
        "richiesta", type=int
    )
    sub.add_parser("respingi", help="respinge una richiesta").add_argument("richiesta", type=int)
    sub.add_parser("revoca", help="revoca il certificato e mette in quarantena").add_argument("id")
    q = sub.add_parser("quarantena", help="un dispositivo, o tutti quelli di un registrante")
    gruppo = q.add_mutually_exclusive_group(required=True)
    gruppo.add_argument("id", nargs="?")
    gruppo.add_argument("--registrante", metavar="MAIL")
    sub.add_parser(
        "cancella-registrante", help="GDPR: revoca e quarantena dei dispositivi, via la mail"
    ).add_argument("email")


async def run(args: argparse.Namespace, *, ca: CaSensori | None = None) -> int:
    settings = get_settings()
    ca = ca or CaSensori(settings.iot.cittadini.registrazione.ca_script)
    async with lifespan_pool():
        await run_migrations()
        comando: dict[str, Callable[[], Awaitable[int]]] = {
            "richieste": richieste,
            "approva": partial(approva, getattr(args, "richiesta", 0), settings=settings, ca=ca),
            "respingi": partial(respingi, getattr(args, "richiesta", 0)),
            "revoca": partial(revoca, getattr(args, "id", ""), ca=ca),
            "quarantena": partial(
                quarantena,
                getattr(args, "id", None),
                registrante=getattr(args, "registrante", None),
            ),
            "cancella-registrante": partial(
                cancella_registrante, getattr(args, "email", ""), ca=ca
            ),
        }
        try:
            return await comando[args.sensore_command]()
        except CaError as exc:
            log.error("sensore.ca", error=str(exc))
            return 1
