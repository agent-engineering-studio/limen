"""Backup dello stato fuori dal server, e ripristino (#304).

Il database è di ~31 GB, ma quasi tutto si ricostruisce: le partizioni di
``risk_assessments`` (15 GB, retention di pochi giorni), gli strati ISPRA
ricaricabili dalle sorgenti (~12 GB), i derivati dello sweep. Quello che non
si ricostruisce — verifiche, eventi e verità, training, sensori, spiegazioni,
dispacci, la catena FWI e i riferimenti GloFAS che costano settimane di quota —
sta in ~2 GB (misurato il 2026-10-24: dump di 202 MB in 36 s, ripristino in
45 s). Il backup salva lo **schema di tutto** e i **dati dello stato**: le
tabelle di ``BACKUP__SOLO_SCHEMA`` tornano vuote, e le riempiono lo sweep, il
bootstrap o la sincronizzazione delle sorgenti.

Un backup è una cartella ``backup/<istante>/`` sullo store del backup:

* ``limen.dump`` — ``pg_dump --format=custom``;
* ``mlflow.dump`` — il registry MLflow, se sta su PostgreSQL nello stesso
  server;
* ``ruoli.sql`` — ``pg_dumpall --roles-only`` senza password: quelle dei
  ruoli ristretti le reimposta l'app all'avvio da ``DB__*_PASSWORD``;
* ``<cartella>.tar.gz`` — le cartelle di ``BACKUP__CARTELLE`` (``mlruns``);
* ``manifest.json`` — scritto per ultimo: un backup senza manifest è un
  backup interrotto, e il ripristino non lo vede. Porta le righe di ogni
  tabella salvata, contate nello stesso snapshot del dump: il ripristino le
  ritrova, o fallisce.

Un ripristino che finisce a metà **solleva** (invariante «Writes do raise»):
``pg_restore`` chiama «errori ignorati» qualunque fallimento SQL, quindi non
basta il suo codice d'uscita. Si ammettono solo gli errori noti e innocui di
``--clean`` (un vincolo ereditato da una partizione, l'estensione da cui ne
dipendono altre), e poi si contano le righe.
"""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import tarfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from limen.config.settings import BackupSettings
from limen.core.logging import get_logger
from limen.data.object_store.base import ObjectStore

log = get_logger(__name__)

PREFISSO = "backup/"
_FORMATO_ISTANTE = "%Y-%m-%dT%H-%M-%SZ"
#: Un dump di qualche GB su un disco lento: un'ora è già un guasto.
_TIMEOUT_SECONDI = 3600.0
#: Gli errori di ``pg_restore --clean`` (o dei ruoli) che non toccano i dati:
#: un vincolo ereditato da una partizione si toglie con la tabella, e
#: ``postgis`` non si toglie se l'immagine ha creato ``postgis_topology``. Ogni
#: altro errore ferma il ripristino.
_ERRORI_AMMESSI = (
    re.compile(r'cannot drop inherited constraint "[^"]+" of relation'),
    re.compile(r"cannot drop extension \w+ because other objects depend on it"),
    re.compile(r'role "[^"]+" already exists'),
    re.compile(r"must be owner of extension \w+"),
)


class BackupError(RuntimeError):
    """Un comando PostgreSQL è fallito, o il ripristino non torna con il manifest."""


@dataclass(frozen=True, slots=True)
class Esito:
    chiave: str
    byte: int
    file: tuple[str, ...]
    cancellati: tuple[str, ...]
    avvisi: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class _Pg:
    """Una connessione per i comandi PostgreSQL: la DSN senza password (che in
    ``ps`` e in ``docker events`` si vedrebbe) e la password a parte."""

    argv0: tuple[str, ...]
    dsn: str
    env: dict[str, str]

    def __call__(self, *argomenti: str) -> list[str]:
        return [*self.argv0, *argomenti]


def _pg(cfg: BackupSettings, dsn: str) -> _Pg:
    parti = urlsplit(dsn)
    env = dict(os.environ)
    prefisso = shlex.split(cfg.comando_pg)
    if parti.password:
        env["PGPASSWORD"] = parti.password
        host = parti.hostname or ""
        utente = f"{parti.username}@" if parti.username else ""
        porta = f":{parti.port}" if parti.port else ""
        dsn = urlunsplit(parti._replace(netloc=f"{utente}{host}{porta}"))
        if "exec" in prefisso and prefisso and Path(prefisso[0]).name == "docker":
            # `-e NOME` senza valore: docker lo prende dall'ambiente del client.
            i = prefisso.index("exec") + 1
            prefisso = [*prefisso[:i], "-e", "PGPASSWORD", *prefisso[i:]]
    return _Pg(argv0=tuple(prefisso), dsn=dsn, env=env)


async def _esegui(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    stdout: Path | None = None,
    stdin: Path | None = None,
    errori_sql: bool = False,
) -> tuple[str, str]:
    """Lancia ``argv``; restituisce (stdout se non va su file, stderr). Un codice
    d'uscita diverso da zero solleva, tranne con ``errori_sql``: ``pg_restore``
    e ``psql`` finiscono il lavoro con errori SQL nel mezzo, e quelli li giudica
    :func:`_errori_non_ammessi` uno per uno."""
    with (
        (stdout or Path(os.devnull)).open("wb") as su_file,
        (stdin or Path(os.devnull)).open("rb") as inp,
    ):
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=inp,
            stdout=su_file if stdout is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(env) if env is not None else None,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_SECONDI)
        except TimeoutError:
            proc.kill()
            # Senza attendere, il processo resta zombie; con `docker exec` il
            # comando dentro il container continua comunque: lo si dice.
            await proc.wait()
            raise BackupError(
                f"{Path(argv[0]).name}: oltre {_TIMEOUT_SECONDI:.0f} s "
                "(con docker exec, controlla che il comando sia finito nel container)"
            ) from None
    if proc.returncode is None:  # pragma: no cover - communicate() attende
        await proc.wait()
    testo = err.decode(errors="replace")
    if proc.returncode != 0 and not (errori_sql and _solo_errori_sql(testo)):
        raise BackupError(f"{Path(argv[0]).name} uscito con {proc.returncode}: {testo[-2000:]}")
    return (out or b"").decode(errors="replace"), testo


def _solo_errori_sql(stderr: str) -> bool:
    """``pg_restore``/``psql`` che hanno eseguito tutto con errori SQL nel mezzo:
    li giudica :func:`_errori_non_ammessi`, non il codice d'uscita."""
    return "errors ignored on restore" in stderr or bool(re.search(r"ERROR:", stderr))


def _errori_non_ammessi(stderr: str) -> list[str]:
    """I messaggi ``ERROR:`` fuori da :data:`_ERRORI_AMMESSI`. Solo la riga del
    messaggio, mai ``Command was:``, che può contenere righe di dati."""
    messaggi = [m.strip() for m in re.findall(r"ERROR:\s+(.+)", stderr)]
    return [m for m in messaggi if not any(a.search(m) for a in _ERRORI_AMMESSI)]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def _tar(cartella: Path, dove: Path, *, nome: str | None = None) -> None:
    with tarfile.open(dove, "w:gz") as tar:
        tar.add(cartella, arcname=nome or cartella.name)


def _estrai(archivio: Path, cartella: Path) -> None:
    """Rimette ``cartella`` com'era nell'archivio, accanto a dove sta."""
    cartella.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archivio, "r:gz") as tar:
        # Il filtro «data» rifiuta path assoluti, `..` e link fuori posto.
        tar.extractall(cartella.parent, filter="data")


def _cartelle(cfg: BackupSettings) -> list[Path]:
    return [Path(c.strip()) for c in cfg.cartelle.split(",") if c.strip()]


def istante(chiave: str) -> datetime | None:
    """L'istante di un backup dalla sua chiave ``backup/<istante>/…``."""
    parti = chiave.removeprefix(PREFISSO).split("/", 1)
    try:
        return datetime.strptime(parti[0], _FORMATO_ISTANTE).replace(tzinfo=UTC)
    except ValueError:
        return None


def _con_database(dsn: str, nome: str) -> str:
    return urlunsplit(urlsplit(dsn)._replace(path=f"/{nome}"))


def _nome_database(dsn: str) -> str | None:
    nome = urlsplit(dsn).path.lstrip("/")
    return nome or None


def mlflow_database(tracking_uri: str) -> str | None:
    """Il database del registry MLflow, se sta su PostgreSQL; ``None`` per
    sqlite o un server remoto (``http://``), che non sono di questo backup."""
    if not tracking_uri.startswith(("postgresql://", "postgresql+")):
        return None
    return _nome_database(tracking_uri)


async def _tabelle_salvate(conn: asyncpg.Connection, cfg: BackupSettings) -> list[str]:
    """Le tabelle di cui il dump porta i dati: tutte, meno quelle solo schema,
    le escluse, le partizioni (contate nel padre) e quelle delle estensioni."""
    nomi: list[str] = [
        r["nome"]
        for r in await conn.fetch(
            """
            SELECT n.nspname || '.' || c.relname AS nome
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
               AND NOT EXISTS (SELECT 1 FROM pg_depend d
                                WHERE d.objid = c.oid AND d.deptype = 'e')
             ORDER BY 1
            """
        )
    ]
    fuori = (*cfg.solo_schema, *cfg.escluse)
    return [n for n in nomi if not any(fnmatch.fnmatchcase(n, p) for p in fuori)]


async def _conta(conn: asyncpg.Connection, tabelle: Sequence[str]) -> dict[str, int]:
    conti: dict[str, int] = {}
    for t in tabelle:
        schema, nome = t.split(".", 1)
        n: int = await conn.fetchval(f'SELECT count(*) FROM "{schema}"."{nome}"')
        conti[t] = n
    return conti


async def esegui_backup(
    *,
    cfg: BackupSettings,
    dsn: str,
    conn: asyncpg.Connection,
    store: ObjectStore,
    adesso: datetime,
    lavoro: Path,
    mlflow: str | None = None,
) -> Esito:
    """Un backup completo su ``store``, poi la retention.

    ``conn`` è sullo stesso database di ``dsn`` (quella dell'app; ``dsn`` è
    come la vedono i comandi, magari da dentro un container). ``mlflow`` è il
    nome del database del registry, nello stesso server.
    """
    base = f"{PREFISSO}{adesso.astimezone(UTC).strftime(_FORMATO_ISTANTE)}/"
    lavoro.mkdir(parents=True, exist_ok=True)
    pg = _pg(cfg, dsn)
    avvisi: list[str] = []
    file: list[Path] = []

    # Conteggi e dump nello stesso snapshot: il manifest dice esattamente
    # quante righe porta il dump, anche se il sistema intanto scrive.
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        snapshot: str = await conn.fetchval("SELECT pg_export_snapshot()")
        conti = await _conta(conn, await _tabelle_salvate(conn, cfg))
        migrazioni: str | None = await conn.fetchval("SELECT max(name) FROM schema_migrations")
        argomenti = [
            "pg_dump",
            "--format=custom",
            "--compress=6",
            "--no-password",
            f"--snapshot={snapshot}",
            f"--dbname={pg.dsn}",
        ]
        argomenti += [f"--exclude-table-data={t}" for t in cfg.solo_schema]
        argomenti += [f"--exclude-table={t}" for t in cfg.escluse]
        await _esegui(pg(*argomenti), env=pg.env, stdout=lavoro / "limen.dump")
    file.append(lavoro / "limen.dump")

    await _esegui(
        pg(
            "pg_dumpall",
            "--roles-only",
            "--no-role-passwords",
            "--no-password",
            f"--dbname={pg.dsn}",
        ),
        env=pg.env,
        stdout=lavoro / "ruoli.sql",
    )
    file.append(lavoro / "ruoli.sql")

    if mlflow is not None:
        if await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", mlflow):
            pg_ml = _pg(cfg, _con_database(dsn, mlflow))
            await _esegui(
                pg_ml("pg_dump", "--format=custom", "--no-password", f"--dbname={pg_ml.dsn}"),
                env=pg_ml.env,
                stdout=lavoro / "mlflow.dump",
            )
            file.append(lavoro / "mlflow.dump")
        else:
            avvisi.append(f"database MLflow «{mlflow}» assente")
            log.warning("backup.mlflow_assente", database=mlflow)

    for cartella in _cartelle(cfg):
        if not cartella.is_dir():
            # Una cartella che manca non ferma il backup del database, che è
            # la parte che conta; finisce negli avvisi del passo.
            avvisi.append(f"cartella {cartella} assente")
            log.warning("backup.cartella_assente", cartella=str(cartella))
            continue
        archivio = lavoro / f"{cartella.name}.tar.gz"
        await asyncio.to_thread(_tar, cartella, archivio)
        file.append(archivio)

    manifest: dict[str, Any] = {
        "creato": adesso.astimezone(UTC).isoformat(),
        "migrazioni": migrazioni,
        "solo_schema": list(cfg.solo_schema),
        "escluse": list(cfg.escluse),
        "righe": conti,
        "mlflow": mlflow if (lavoro / "mlflow.dump") in file else None,
        "file": {},
    }
    for f in file:
        impronta = await asyncio.to_thread(_sha256, f)
        manifest["file"][f.name] = {"byte": f.stat().st_size, "sha256": impronta}
        await store.put_file(base + f.name, f)
    # Il manifest per ultimo: è ciò che rende il backup «completo».
    await store.put(
        base + "manifest.json",
        json.dumps(manifest, indent=1).encode(),
        content_type="application/json",
    )
    cancellati: list[str] = []
    try:
        if await _crollato(store, cfg, conti, escludi=base):
            avvisi.append("righe di stato crollate rispetto al precedente: retention sospesa")
        else:
            cancellati = await pulisci(store, cfg, adesso)
    except Exception as exc:
        # Il backup c'è: una retention che fallisce non lo rende «non fatto».
        avvisi.append(f"retention non riuscita: {type(exc).__name__}")
        log.warning("backup.retention_fallita", error=str(exc))
    totale = sum(v["byte"] for v in manifest["file"].values())
    log.info("backup.fatto", chiave=base, byte=totale, cancellati=len(cancellati), avvisi=avvisi)
    return Esito(
        chiave=base,
        byte=totale,
        file=tuple(manifest["file"]),
        cancellati=tuple(cancellati),
        avvisi=tuple(avvisi),
    )


async def _crollato(
    store: ObjectStore, cfg: BackupSettings, conti: Mapping[str, int], *, escludi: str
) -> bool:
    """Le righe di stato sotto ``soglia_crollo`` del backup precedente: un volume
    ricreato vuoto, o il database sbagliato. Allora la retention aspetta, o in
    ``retention_giorni`` i backup buoni uscirebbero dal bucket."""
    precedenti = [c for c in await backup_completi(store) if c != escludi]
    if not precedenti:
        return False
    prima: dict[str, int] = (
        json.loads(await store.get(precedenti[-1] + "manifest.json")).get("righe") or {}
    )
    totale_prima = sum(prima.values())
    return totale_prima > 0 and sum(conti.values()) < cfg.soglia_crollo * totale_prima


async def backup_completi(store: ObjectStore) -> list[str]:
    """Le cartelle ``backup/<istante>/`` con il manifest, dalla più vecchia."""
    return sorted(
        k.removesuffix("manifest.json")
        for k in await store.list(PREFISSO)
        if k.endswith("/manifest.json")
    )


async def pulisci(store: ObjectStore, cfg: BackupSettings, adesso: datetime) -> list[str]:
    """Cancella i backup oltre ``retention_giorni``, tenendo sempre gli ultimi
    ``tieni_almeno`` completi; e i backup interrotti più vecchi di un giorno."""
    chiavi = await store.list(PREFISSO)
    completi = await backup_completi(store)
    salvi = set(completi[-cfg.tieni_almeno :])
    limite = adesso - timedelta(days=cfg.retention_giorni)
    cartelle = sorted({PREFISSO + k.removeprefix(PREFISSO).split("/", 1)[0] + "/" for k in chiavi})
    via: list[str] = []
    for cartella in cartelle:
        quando = istante(cartella)
        if quando is None or cartella in salvi:
            continue
        interrotto = cartella not in completi
        if quando < limite or (interrotto and quando < adesso - timedelta(days=1)):
            for k in chiavi:
                if k.startswith(cartella):
                    await store.delete(k)
            via.append(cartella)
    return via


async def _livello(conn: asyncpg.Connection) -> str | None:
    if await conn.fetchval("SELECT to_regclass('public.schema_migrations')") is None:
        return None
    livello: str | None = await conn.fetchval("SELECT max(name) FROM schema_migrations")
    return livello


async def ripristina(
    *,
    cfg: BackupSettings,
    dsn: str,
    conn: asyncpg.Connection,
    store: ObjectStore,
    lavoro: Path,
    chiave: str | None = None,
    forza: bool = False,
) -> str:
    """Ripristina il backup ``chiave`` (l'ultimo completo se ``None``) nel
    database di ``dsn``; ``conn`` è sullo stesso database. Solleva
    :class:`BackupError` se il risultato non è il backup: un ripristino a metà
    non finisce mai con «fatto». Restituisce la chiave ripristinata."""
    completi = await backup_completi(store)
    if chiave is None:
        if not completi:
            raise BackupError("nessun backup completo sullo store")
        chiave = completi[-1]
    elif not chiave.endswith("/"):
        chiave += "/"
    if chiave not in completi:
        raise BackupError(f"{chiave} non è un backup completo (manca il manifest)")
    manifest = json.loads(await store.get(chiave + "manifest.json"))

    altri: int = await conn.fetchval(
        """
        SELECT count(*) FROM pg_stat_activity
         WHERE datname = current_database() AND pid <> pg_backend_pid()
           AND backend_type = 'client backend'
        """
    )
    if altri and not forza:
        raise BackupError(f"{altri} client connessi al database: ferma API e worker (o --forza)")
    livello = await _livello(conn)
    if livello is not None and livello != manifest.get("migrazioni") and not forza:
        # Un --clean di uno schema più vecchio lascerebbe le tabelle nuove e
        # riporterebbe `schema_migrations` indietro: al boot l'API riapplicherebbe
        # migrazioni su oggetti che esistono già.
        raise BackupError(
            f"il database è alla migrazione {livello}, il backup a "
            f"{manifest.get('migrazioni')}: ripristina su un database vuoto (o --forza)"
        )

    lavoro.mkdir(parents=True, exist_ok=True)
    for nome, atteso in manifest["file"].items():
        if Path(nome).name != nome:
            raise BackupError(f"nome di file non valido nel manifest: {nome!r}")
        dove = lavoro / nome
        await store.get_file(chiave + nome, dove)
        if await asyncio.to_thread(_sha256, dove) != atteso["sha256"]:
            raise BackupError(f"{nome}: lo sha256 non è quello del manifest")

    pg = _pg(cfg, dsn)
    # I ruoli prima delle tabelle, o i GRANT ai ruoli ristretti fallirebbero.
    _, err = await _esegui(
        pg("psql", "--no-password", "--quiet", f"--dbname={pg.dsn}"),
        env=pg.env,
        stdin=lavoro / "ruoli.sql",
        errori_sql=True,
    )
    if cattivi := _errori_non_ammessi(err):
        raise BackupError(f"ruoli: {'; '.join(cattivi[:5])}")
    _, err = await _esegui(
        pg(
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-password",
            f"--dbname={pg.dsn}",
        ),
        env=pg.env,
        stdin=lavoro / "limen.dump",
        errori_sql=True,
    )
    if cattivi := _errori_non_ammessi(err):
        raise BackupError(f"pg_restore: {len(cattivi)} errori, fra cui {'; '.join(cattivi[:5])}")

    # Il dump dice quante righe porta: se non ci sono, il ripristino non è fatto.
    attese: dict[str, int] = manifest.get("righe") or {}
    trovate = await _conta(conn, list(attese))
    diverse = {t: (n, trovate.get(t)) for t, n in attese.items() if trovate.get(t) != n}
    if diverse:
        esempio = ", ".join(f"{t}: {a}≠{b}" for t, (a, b) in list(diverse.items())[:5])
        raise BackupError(f"{len(diverse)} tabelle con righe diverse dal backup: {esempio}")

    # Le tabelle solo schema tornano vuote, ma le loro versioni in
    # `dataset_versions` tornano piene: senza toglierle, il loader direbbe
    # «già caricato» e le lascerebbe vuote (invariante dell'idempotenza).
    if cfg.versioni_da_dimenticare:
        await conn.execute(
            "DELETE FROM dataset_versions WHERE source || ':' || dataset LIKE ANY($1::text[])",
            list(cfg.versioni_da_dimenticare),
        )

    if manifest.get("mlflow") and "mlflow.dump" in manifest["file"]:
        nome = str(manifest["mlflow"])
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", nome):
            await conn.execute(f'CREATE DATABASE "{nome}"')
        pg_ml = _pg(cfg, _con_database(dsn, nome))
        _, err = await _esegui(
            pg_ml(
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-password",
                f"--dbname={pg_ml.dsn}",
            ),
            env=pg_ml.env,
            stdin=lavoro / "mlflow.dump",
            errori_sql=True,
        )
        if cattivi := _errori_non_ammessi(err):
            raise BackupError(f"MLflow: {'; '.join(cattivi[:5])}")

    per_nome = {c.name: c for c in _cartelle(cfg)}
    for nome in manifest["file"]:
        if not nome.endswith(".tar.gz"):
            continue
        cartella = per_nome.get(nome.removesuffix(".tar.gz"))
        if cartella is None:
            # Salvata da un server che la configurava, qui no: resta scaricata.
            log.info("backup.cartella_non_configurata", file=str(lavoro / nome))
            continue
        await asyncio.to_thread(_estrai, lavoro / nome, cartella)
        log.info("backup.cartella_ripristinata", cartella=str(cartella))
    log.info(
        "backup.ripristinato",
        chiave=chiave,
        migrazioni=manifest.get("migrazioni"),
        tabelle=len(attese),
    )
    return chiave


# --- La CA dei sensori, cifrata (#304) -------------------------------------
#
# La chiave della CA firma i certificati di ogni sensore: in chiaro su un
# bucket sarebbe la rete intera. Esce dal server solo cifrata, con una chiave
# ricavata dalla passphrase con scrypt (lento apposta: una passphrase si prova
# per forza bruta) e AES-256-GCM, che rifiuta un file alterato o una
# passphrase sbagliata invece di restituire spazzatura.

_FIRMA_CA = b"LIMENCA1"
#: Il minimo OWASP per scrypt (r=8, p=1): 128 MiB, una volta per firma.
_SCRYPT_N = 2**17


def _chiave(passphrase: str, sale: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=sale, length=32, n=_SCRYPT_N, r=8, p=1).derive(passphrase.encode())


def cifra(dati: bytes, passphrase: str) -> bytes:
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    sale, nonce = os.urandom(16), os.urandom(12)
    return _FIRMA_CA + sale + nonce + AESGCM(_chiave(passphrase, sale)).encrypt(nonce, dati, None)


def decifra(blob: bytes, passphrase: str) -> bytes:
    """Solleva :class:`BackupError` con una passphrase sbagliata o un file alterato."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(_FIRMA_CA):
        raise BackupError("non è un backup cifrato della CA")
    testa = len(_FIRMA_CA)
    sale, nonce, corpo = blob[testa : testa + 16], blob[testa + 16 : testa + 28], blob[testa + 28 :]
    try:
        return AESGCM(_chiave(passphrase, sale)).decrypt(nonce, corpo, None)
    except InvalidTag:
        raise BackupError("passphrase sbagliata, o file alterato") from None


def archivio_cartella(cartella: Path) -> bytes:
    """La cartella come tar.gz in memoria (la CA pesa pochi KB)."""
    import io

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Sempre «ca», qualunque sia il nome della cartella: il ripristino
        # controlla `dove/ca` per non sovrascrivere una CA che esiste.
        tar.add(cartella, arcname="ca")
    return buf.getvalue()


def estrai_archivio(dati: bytes, dove: Path) -> None:
    import io

    dove.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(dati), mode="r:gz") as tar:
        tar.extractall(dove, filter="data")


__all__ = [
    "PREFISSO",
    "BackupError",
    "Esito",
    "archivio_cartella",
    "backup_completi",
    "cifra",
    "decifra",
    "esegui_backup",
    "estrai_archivio",
    "istante",
    "mlflow_database",
    "pulisci",
    "ripristina",
]
