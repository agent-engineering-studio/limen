"""``limen sensore …`` — l'operatore decide sulle richieste dei sensori (#253).

    limen sensore richieste                       le richieste in attesa
    limen sensore approva <richiesta>             firma la CSR, crea il dispositivo, manda il cert
    limen sensore respingi <richiesta>
    limen sensore revoca <id>                     revoca il certificato e mette in quarantena
    limen sensore quarantena <id>
    limen sensore quarantena --registrante <mail> tutti i dispositivi di un registrante
    limen sensore cancella-registrante <mail>     GDPR: revoca, quarantena, cancella la mail
    limen sensore ttn-segreto <applicazione>      nuovo segreto del webhook TTN, per mail
    limen sensore backup-ca                       la CA, cifrata, sullo store del backup
    limen sensore ripristina-ca --dove <cartella> [--chiave ca-sensori/…]

Gira **sull'host**, dalla radice del repo: firmare e revocare passano da
``scripts/sensori_ca.sh``, perché la chiave della CA vive in
``$LIMEN_SENSORI_DIR/ca`` e non entra in nessun container.

Tutti idempotenti: ``approva`` su una richiesta già approvata rimanda la
mail con lo stesso certificato invece di firmarne un altro; revocare,
mettere in quarantena o cancellare due volte non cambia niente.

Dopo ogni firma e ogni revoca la CA si salva da sola, cifrata con
``BACKUP__PASSPHRASE_CA``, sullo store del backup (#304): era l'unica cosa
della rete senza copia fuori dal server. Senza store o passphrase, lo dice.

Un sensore LoRaWAN (#266) non ha certificato: approvarlo crea, se manca,
l'applicazione TTN del registrante con un segreto per il webhook, che parte
nella mail e di cui resta solo lo SHA-256. Rilanciare ``approva`` rimanda la
mail ma non il segreto: se la prima mail non è partita, o il segreto è perso,
``ttn-segreto`` ne genera uno nuovo.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import secrets
import tempfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import asyncpg

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.core.sensori_registrazione import TIPO_IT, leggi_csr
from limen.data.backup import (
    BackupError,
    archivio_cartella,
    cifra,
    decifra,
    estrai_archivio,
)
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.object_store import build_backup_store
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


def _istruzioni_webhook(applicazione: str, *, webhook: str, segreto: str | None) -> list[str]:
    if segreto is None:
        # Anche quando la mail con il segreto non è partita: Limen non lo ha
        # più, e il rimedio è generarne uno nuovo.
        return [
            f"Il webhook dell'applicazione {applicazione} è già registrato: vale il",
            "segreto che hai ricevuto per mail. Se non l'hai ricevuto, o l'hai perso,",
            "rispondi a questa mail: ne generiamo uno nuovo.",
        ]
    return [
        f"Nella console di The Things Network, applicazione {applicazione},",
        "aggiungi un webhook (Integrations → Webhooks → Custom webhook):",
        "",
        "  Formato:          JSON",
        f"  URL base:         {webhook}",
        f"  Header:           Authorization: Bearer {segreto}",
        "  Uplink message:   attivo, percorso vuoto",
        "",
        f"Il segreto vale per tutti i dispositivi dell'applicazione {applicazione}.",
        "Tienilo come una password: chi lo conosce parla a nome dei tuoi sensori.",
        "Limen ne conserva solo l'impronta: se lo perdi, rispondi a questa mail e",
        "ne generiamo uno nuovo.",
    ]


def mail_lorawan(r: repo.Richiesta, *, webhook: str, segreto: str | None) -> tuple[str, str]:
    assert r.ttn_applicazione is not None
    oggetto = f"[Limen] Il tuo sensore {r.device_id} è registrato"
    testo = "\n".join(
        [
            f"Il sensore {r.device_id} ({TIPO_IT.get(r.device_type, r.device_type)}, "
            f"DevEUI {r.dev_eui}) è nel registro di Limen.",
            "",
            *_istruzioni_webhook(r.ttn_applicazione, webhook=webhook, segreto=segreto),
            "",
            "Il payload è SenML in CBOR (RFC 8428), con l'id del dispositivo nei nomi",
            "e un record seq: il protocollo è nella pagina Sensori di Limen. Il",
            "payload formatter di TTN non serve, Limen legge i byte del dispositivo.",
            "",
            "Il sensore parte come osservatore (livello 0): le sue misure si salvano",
            "e si confrontano con il radar, ma non cambiano i punteggi né le allerte.",
            "",
            "Per cancellare la registrazione e i tuoi dati basta rispondere a questa mail.",
        ]
    )
    return oggetto, testo


def _segreto() -> tuple[str, bytes]:
    segreto = secrets.token_urlsafe(32)
    return segreto, hashlib.sha256(segreto.encode()).digest()


async def _approva_lorawan(r: repo.Richiesta, *, settings: Settings) -> int:
    assert r.ttn_applicazione is not None
    segreto: str | None = None
    if r.stato == "in_attesa":
        if await sensor_devices_repo.get_device(r.device_id) is not None:
            log.error("sensore.id_in_uso", device_id=r.device_id)
            return 1
        cell_id = r.cell_id or await repo.cella_per_punto(r.lon, r.lat)
        if cell_id is None:
            log.error("sensore.fuori_griglia", richiesta=r.id, lon=r.lon, lat=r.lat)
            return 1
        candidato, impronta = _segreto()
        try:
            nuova = await repo.approva_lorawan(r, cell_id=cell_id, segreto_sha256=impronta)
        except repo.ApplicazioneAltruiError:
            log.error("sensore.applicazione_altrui", applicazione=r.ttn_applicazione)
            return 1
        except asyncpg.UniqueViolationError as exc:
            # L'id o il DevEUI, preso nel frattempo da un altro dispositivo.
            log.error(
                "sensore.gia_in_uso",
                device_id=r.device_id,
                dev_eui=r.dev_eui,
                vincolo=exc.constraint_name,
            )
            return 1
        if nuova is None:
            log.error("sensore.gia_decisa", richiesta=r.id)
            return 1
        segreto = candidato if nuova else None
        log.info(
            "sensore.approvato",
            richiesta=r.id,
            device_id=r.device_id,
            cell_id=cell_id,
            applicazione_nuova=nuova,
        )
    else:
        dispositivo = await sensor_devices_repo.get_device(r.device_id)
        if dispositivo is not None and dispositivo.status == "quarantined":
            log.error("sensore.in_quarantena", device_id=r.device_id)
            return 1

    oggetto, testo = mail_lorawan(
        r, webhook=settings.iot.cittadini.registrazione.webhook_ttn_pubblico, segreto=segreto
    )
    partita = await invia_testo(
        settings.notifications.email, destinatari=[r.email], oggetto=oggetto, testo=testo
    )
    if not partita:
        # Un segreto nuovo che non è partito è perso: se ne genera un altro.
        rimedio = (
            f"limen sensore ttn-segreto {r.ttn_applicazione}"
            if segreto is not None
            else f"limen sensore approva {r.id}"
        )
        log.error("sensore.mail_non_partita", device_id=r.device_id, rimedio=rimedio)
        return 1
    log.info("sensore.registrazione_inviata", device_id=r.device_id)
    return 0


async def ttn_segreto(applicazione: str, *, settings: Settings) -> int:
    segreto, impronta = _segreto()
    email = await repo.ruota_segreto_ttn(applicazione, impronta)
    if email is None:
        log.error("sensore.applicazione_sconosciuta", applicazione=applicazione)
        return 1
    testo = "\n".join(
        [
            f"Il segreto del webhook dell'applicazione {applicazione} è cambiato:",
            "quello di prima non vale più. Aggiorna l'header del webhook.",
            "",
            *_istruzioni_webhook(
                applicazione,
                webhook=settings.iot.cittadini.registrazione.webhook_ttn_pubblico,
                segreto=segreto,
            ),
        ]
    )
    partita = await invia_testo(
        settings.notifications.email,
        destinatari=[email],
        oggetto=f"[Limen] Nuovo segreto per il webhook di {applicazione}",
        testo=testo,
    )
    if not partita:
        log.error(
            "sensore.mail_non_partita",
            applicazione=applicazione,
            rimedio=f"rilancia `limen sensore ttn-segreto {applicazione}`",
        )
        return 1
    log.info("sensore.segreto_ttn_ruotato", applicazione=applicazione)
    return 0


async def approva(richiesta_id: int, *, settings: Settings, ca: CaSensori) -> int:
    r = await repo.richiesta(richiesta_id)
    if r is None:
        log.error("sensore.richiesta_sconosciuta", richiesta=richiesta_id)
        return 1
    if r.stato == "respinta":
        log.error("sensore.richiesta_respinta", richiesta=richiesta_id)
        return 1
    if r.csr is None:
        return await _approva_lorawan(r, settings=settings)
    csr = r.csr
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
                csr, giorni=settings.iot.cittadini.registrazione.giorni_certificato
            )
            await repo.salva_certificato(r.id, certificato)
        if not await repo.approva(
            r, cell_id=cell_id, certificato=certificato, chiave=leggi_csr(csr).chiave
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
            r.device_id, leggi_csr(csr).chiave
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


_PREFISSO_CA = "ca-sensori/"
#: I comandi che cambiano la CA: dopo, la si salva.
_CAMBIANO_LA_CA = frozenset({"approva", "revoca", "cancella-registrante"})


def _cartella_ca(settings: Settings) -> Path | None:
    if settings.backup.cartella_ca is not None:
        return settings.backup.cartella_ca
    radice = os.getenv("LIMEN_SENSORI_DIR")
    return Path(radice) / "ca" if radice else None


async def backup_ca(settings: Settings) -> int:
    """La CA dei sensori, cifrata, sullo store del backup (#304)."""
    cfg = settings.backup
    store = build_backup_store(cfg)
    cartella = _cartella_ca(settings)
    if store is None or cfg.passphrase_ca is None or cartella is None:
        log.warning(
            "sensore.ca_senza_backup",
            hint="BACKUP__BUCKET, BACKUP__PASSPHRASE_CA e LIMEN_SENSORI_DIR: "
            "senza, la CA ha solo la copia su questo server",
        )
        return 1
    if not (cartella / "ca.key").exists():
        log.error("sensore.ca_assente", cartella=str(cartella))
        return 1
    blob = cifra(archivio_cartella(cartella), cfg.passphrase_ca.get_secret_value())
    chiave = f"{_PREFISSO_CA}{datetime.now(UTC).strftime('%Y-%m-%dT%H-%M-%SZ')}.tar.gz.enc"
    await store.put(chiave, blob, content_type="application/octet-stream")
    log.info("sensore.ca_salvata", chiave=chiave, byte=len(blob))
    return 0


async def ripristina_ca(settings: Settings, *, dove: Path, chiave: str | None) -> int:
    """Rimette la CA in ``dove/ca``. Non sovrascrive una CA che c'è già."""
    cfg = settings.backup
    store = build_backup_store(cfg)
    if store is None or cfg.passphrase_ca is None:
        log.error("sensore.ca_senza_backup", hint="BACKUP__BUCKET e BACKUP__PASSPHRASE_CA")
        return 1
    if (dove / "ca").exists() and any((dove / "ca").iterdir()):
        log.error("sensore.ca_esiste", cartella=str(dove / "ca"), hint="scegli un'altra --dove")
        return 1
    if chiave is None:
        salvate = await store.list(_PREFISSO_CA)
        if not salvate:
            log.error("sensore.ca_nessun_backup")
            return 1
        chiave = salvate[-1]
    try:
        dati = decifra(await store.get(chiave), cfg.passphrase_ca.get_secret_value())
    except BackupError as exc:
        log.error("sensore.ca_illeggibile", chiave=chiave, error=str(exc))
        return 1
    estrai_archivio(dati, dove)
    log.info("sensore.ca_ripristinata", chiave=chiave, cartella=str(dove / "ca"))
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
    sub.add_parser(
        "ttn-segreto", help="nuovo segreto del webhook di un'applicazione TTN (#266)"
    ).add_argument("applicazione")
    sub.add_parser("backup-ca", help="la CA, cifrata, sullo store del backup (#304)")
    rc = sub.add_parser("ripristina-ca", help="la CA da un backup cifrato (#304)")
    rc.add_argument("--dove", type=Path, required=True, help="cartella in cui ricreare ca/")
    rc.add_argument("--chiave", help="ca-sensori/<istante>.tar.gz.enc (default: l'ultimo)")


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
            "ttn-segreto": partial(
                ttn_segreto, getattr(args, "applicazione", ""), settings=settings
            ),
            "backup-ca": partial(backup_ca, settings),
            "ripristina-ca": partial(
                ripristina_ca,
                settings,
                dove=getattr(args, "dove", Path()),
                chiave=getattr(args, "chiave", None),
            ),
        }
        try:
            return await comando[args.sensore_command]()
        except CaError as exc:
            log.error("sensore.ca", error=str(exc))
            return 1
        finally:
            if args.sensore_command in _CAMBIANO_LA_CA:
                # Qualunque sia l'esito: la firma può riuscire e la mail no, la
                # revoca riuscire e il database no, e la CA è cambiata comunque
                # (Codex, #311). Salvarne una uguale costa pochi KB. Il backup
                # non decide l'esito del comando.
                try:
                    await backup_ca(settings)
                except Exception as exc:
                    log.warning("sensore.ca_backup_fallito", error=str(exc))
