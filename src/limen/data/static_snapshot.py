"""Snapshot dello strato statico: i fattori per cella senza i raster (#305).

Il sistema operativo non legge il DTM, CORINE o la carta geolitologica: legge
``cell_static_factors``, che il bootstrap ne ricava in 1,5-2 ore da ~47 GB di
sorgenti. Uno snapshot porta solo il risultato, così un'istanza **nuova** (non
il ripristino di questa: per quello c'è il backup notturno, #304) ha i fattori
in minuti e senza scaricare un raster.

Cosa porta:

* ``cell_static_factors`` — i fattori per cella;
* ``flood_hazard_subdiv`` — il mosaico idraulico ISPRA, che la mappa disegna
  come strato a sé (pg_tileserv). PAI e IFFI no: servono solo al bootstrap, e
  la mappa li prende dal WMS di GeoServer;
* ``fire_events`` — lo storico FIRMS da cui viene la densità degli incendi;
* le impronte del bootstrap (``dataset_versions`` di ``static_bootstrap``).
  Un server che poi mette le sorgenti allo stesso percorso con ``rsync -a``
  (stesso mtime, stessa dimensione) ritrova le stesse impronte e non ricalcola.

L'import si aggancia alla griglia di destinazione: gli id delle celle sono
deterministici (AOI, riga, colonna), quindi dopo ``limen seed`` coincidono —
e l'import lo verifica per AOI prima di scrivere, insieme alla migrazione.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg

from limen.config.settings import BackupSettings
from limen.core.logging import get_logger
from limen.data.backup import (
    BackupError,
    _conta,
    _esegui,
    _livello,
    _Pg,
    _pg,
    _sha256,
)
from limen.data.object_store import ObjectStore
from limen.integrations.static_bootstrap.fingerprint import SOURCE as BOOTSTRAP_SOURCE

log = get_logger(__name__)

PREFISSO = "statico/"
TABELLE = (
    "public.cell_static_factors",
    "public.flood_hazard_subdiv",
    # Lo storico degli incendi (FIRMS) da cui viene la densità per cella:
    # senza, il passo `fire_density` del bootstrap — che accetta una tabella
    # vuota come risposta legittima — la ricalcolerebbe a zero subito dopo
    # l'import (Codex, #333). 83 MB.
    "public.fire_events",
)
_DUMP = "statico.dump"
_FORMATO_ISTANTE = "%Y-%m-%dT%H-%M-%SZ"


@dataclass(frozen=True, slots=True)
class Snapshot:
    chiave: str
    byte: int
    righe: dict[str, int]


async def _griglia(conn: asyncpg.Connection) -> dict[str, dict[str, Any]]:
    """Per AOI: quante celle e un'impronta di id **e posizione**.

    Gli id dicono solo AOI, riga e colonna, e la griglia parte dall'angolo
    dell'AOI: un confine ridisegnato sposta ogni cella lasciando gli stessi
    id, e i fattori finirebbero nel posto sbagliato (Codex, #333). L'angolo di
    ogni cella entra nell'impronta, arrotondato a 1e-6 gradi (~10 cm): il
    rumore di virgola mobile fra due macchine non deve contare, un metro sì.
    """
    righe = await conn.fetch(
        """
        SELECT aoi_id, count(*) AS celle,
               md5(string_agg(
                   id || ':' || round(ST_XMin(geom)::numeric, 6)
                      || ':' || round(ST_YMin(geom)::numeric, 6),
                   ',' ORDER BY id)) AS impronta
          FROM grid_cells GROUP BY aoi_id
        """
    )
    return {r["aoi_id"]: {"celle": r["celle"], "impronta": r["impronta"]} for r in righe}


async def esporta(
    *,
    cfg: BackupSettings,
    dsn: str,
    conn: asyncpg.Connection,
    store: ObjectStore,
    adesso: datetime,
    lavoro: Path,
) -> Snapshot:
    """Uno snapshot su ``store``, sotto ``statico/<istante>/``."""
    base = f"{PREFISSO}{adesso.astimezone(UTC).strftime(_FORMATO_ISTANTE)}/"
    lavoro.mkdir(parents=True, exist_ok=True)
    pg = _pg(cfg, dsn)
    dump = lavoro / _DUMP
    # Dump, conteggi, griglia e impronte nella stessa fotografia del database.
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        fotografia: str = await conn.fetchval("SELECT pg_export_snapshot()")
        righe = await _conta(conn, list(TABELLE))
        if not righe["public.cell_static_factors"]:
            raise BackupError("cell_static_factors è vuota: niente da esportare")
        migrazioni = await _livello(conn)
        griglia = await _griglia(conn)
        impronte = [
            dict(r)
            for r in await conn.fetch(
                """
                SELECT dataset, version, metadata::text AS metadata
                  FROM dataset_versions WHERE source = $1 ORDER BY dataset, fetched_at
                """,
                BOOTSTRAP_SOURCE,
            )
        ]
        tabelle = [a for t in TABELLE for a in ("--table", t)]
        await _esegui(
            pg(
                "pg_dump",
                "--format=custom",
                "--compress=6",
                "--data-only",
                "--no-password",
                f"--snapshot={fotografia}",
                *tabelle,
                f"--dbname={pg.dsn}",
            ),
            env=pg.env,
            stdout=dump,
        )
    byte = dump.stat().st_size
    manifest = {
        "creato": adesso.astimezone(UTC).isoformat(),
        "migrazioni": migrazioni,
        "righe": righe,
        "griglia": griglia,
        "impronte": impronte,
        "file": {_DUMP: {"byte": byte, "sha256": await asyncio.to_thread(_sha256, dump)}},
    }
    await store.put_file(base + _DUMP, dump)
    # Il manifest per ultimo, come nel backup: è ciò che rende lo snapshot completo.
    await store.put(
        base + "manifest.json",
        json.dumps(manifest, indent=1).encode(),
        content_type="application/json",
    )
    log.info("static_snapshot.esportato", chiave=base, byte=byte, righe=righe, aoi=len(griglia))
    return Snapshot(chiave=base, byte=byte, righe=righe)


async def snapshot_completi(store: ObjectStore) -> list[str]:
    """Le cartelle ``statico/<istante>/`` con il manifest, dalla più vecchia."""
    chiavi = await store.list(PREFISSO)
    return sorted(k.removesuffix("manifest.json") for k in chiavi if k.endswith("/manifest.json"))


def _letterale(valore: str) -> str:
    return "'" + valore.replace("'", "''") + "'"


def _preludio(tabelle: list[str]) -> str:
    # Le impronte del bootstrap di qui descrivono i fattori che si stanno per
    # sostituire: lasciate, il bootstrap salterebbe un ricalcolo dovuto (Codex,
    # #333). Vanno via nella stessa transazione dei dati.
    return (
        f"TRUNCATE {', '.join(tabelle)};\n"
        f"DELETE FROM public.dataset_versions WHERE source = {_letterale(BOOTSTRAP_SOURCE)};\n"
    )


def _epilogo(attese: dict[str, int], impronte: list[dict[str, str]]) -> str:
    """Il controllo delle righe e le impronte dello snapshot, dentro la stessa
    transazione: righe diverse fanno fallire tutto, impronte comprese."""
    righe = [
        f"IF (SELECT count(*) FROM {t}) <> {int(n)} THEN "
        f"RAISE EXCEPTION 'righe diverse dallo snapshot in {t}'; END IF;"
        for t, n in attese.items()
    ]
    valori = ",\n".join(
        f"({_letterale(BOOTSTRAP_SOURCE)}, {_letterale(i['dataset'])}, "
        f"{_letterale(i['version'])}, {_letterale(i['metadata'])}::jsonb)"
        for i in impronte
    )
    insert = (
        "INSERT INTO public.dataset_versions (source, dataset, version, metadata) VALUES\n"
        f"{valori};\n"
        if impronte
        else ""
    )
    return "DO $$ BEGIN\n" + "\n".join(righe) + "\nEND $$;\n" + insert


async def _carica(pg: _Pg, dump: Path, *, prima: str, dopo: str) -> None:
    """Preludio, dati di ``pg_restore`` e epilogo in **una** transazione di psql.

    Con il ``TRUNCATE`` su una connessione a parte, un caricamento fallito
    lasciava le tabelle vuote (Codex, #333). Qui ``pg_restore`` scrive l'SQL e
    psql lo esegue in streaming con ``--single-transaction`` e
    ``ON_ERROR_STOP``: o tutto, o i dati di prima. Se ``pg_restore`` stesso
    fallisce, psql viene ucciso prima della fine dell'input, così la
    transazione non arriva al COMMIT.
    """
    psql = await asyncio.create_subprocess_exec(
        *pg(
            "psql",
            "--no-password",
            "--quiet",
            "--single-transaction",
            "--set=ON_ERROR_STOP=1",
            f"--dbname={pg.dsn}",
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=pg.env,
    )
    assert psql.stdin is not None and psql.stderr is not None
    errori_psql = asyncio.create_task(psql.stderr.read())
    with dump.open("rb") as sorgente:
        restore = await asyncio.create_subprocess_exec(
            *pg("pg_restore", "--data-only", "--no-owner", "--file=-"),
            stdin=sorgente,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=pg.env,
        )
        assert restore.stdout is not None and restore.stderr is not None
        errori_restore = asyncio.create_task(restore.stderr.read())
        interrotto = False
        try:
            psql.stdin.write(prima.encode())
            while blocco := await restore.stdout.read(1 << 20):
                psql.stdin.write(blocco)
                await psql.stdin.drain()
            if await restore.wait() != 0:
                interrotto = True
                psql.kill()
            else:
                psql.stdin.write(dopo.encode())
                await psql.stdin.drain()
                psql.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
            # psql si è fermato su un errore: lo dice il suo stderr.
            restore.kill()
            await restore.wait()
    codice = await psql.wait()
    err_psql = (await errori_psql).decode(errors="replace")
    err_restore = (await errori_restore).decode(errors="replace")
    if interrotto:
        raise BackupError(f"pg_restore: {err_restore[-2000:]} — nessun dato toccato")
    if codice != 0:
        raise BackupError(f"psql uscito con {codice}: {err_psql[-2000:]} — nessun dato toccato")


async def importa(
    *,
    cfg: BackupSettings,
    dsn: str,
    conn: asyncpg.Connection,
    store: ObjectStore,
    lavoro: Path,
    chiave: str | None = None,
    forza: bool = False,
) -> Snapshot:
    """Carica lo snapshot ``chiave`` (l'ultimo se ``None``) nel database di
    ``dsn``. Solleva :class:`BackupError` se la destinazione non è compatibile
    o se le righe caricate non sono quelle del manifest."""
    completi = await snapshot_completi(store)
    if chiave is None:
        if not completi:
            raise BackupError("nessuno snapshot statico sullo store")
        chiave = completi[-1]
    elif not chiave.endswith("/"):
        chiave += "/"
    if chiave not in completi:
        raise BackupError(f"{chiave} non è uno snapshot completo (manca il manifest)")
    manifest = json.loads(await store.get(chiave + "manifest.json"))

    livello = await _livello(conn)
    if livello != manifest["migrazioni"]:
        # Le colonne di cell_static_factors cambiano con le migrazioni: un dump
        # di un altro schema caricherebbe a metà o non caricherebbe.
        raise BackupError(
            f"il database è alla migrazione {livello}, lo snapshot a "
            f"{manifest['migrazioni']}: aggiorna (limen migrate) o prendi uno snapshot più recente"
        )
    qui = await _griglia(conn)
    diverse = [aoi for aoi, g in manifest["griglia"].items() if qui.get(aoi) != g]
    if diverse:
        raise BackupError(
            f"griglia diversa da quella dello snapshot in {len(diverse)} AOI "
            f"({', '.join(sorted(diverse)[:5])}): lancia prima limen seed"
        )
    gia = await _conta(conn, ["public.cell_static_factors"])
    if gia["public.cell_static_factors"] and not forza:
        raise BackupError(
            f"cell_static_factors ha già {gia['public.cell_static_factors']} righe: "
            "lo snapshot le sostituirebbe (--forza)"
        )

    lavoro.mkdir(parents=True, exist_ok=True)
    dump = lavoro / _DUMP
    await store.get_file(chiave + _DUMP, dump)
    if await asyncio.to_thread(_sha256, dump) != manifest["file"][_DUMP]["sha256"]:
        raise BackupError(f"{_DUMP}: lo sha256 non è quello del manifest")

    attese: dict[str, int] = manifest["righe"]
    await _carica(
        _pg(cfg, dsn),
        dump,
        prima=_preludio(list(attese)),
        dopo=_epilogo(attese, manifest["impronte"]),
    )
    trovate = await _conta(conn, list(attese))
    log.info(
        "static_snapshot.importato",
        chiave=chiave,
        righe=trovate,
        impronte=len(manifest["impronte"]),
        hint="poi limen calibrate: le statistiche per AOI non sono nello snapshot",
    )
    return Snapshot(chiave=chiave, byte=int(manifest["file"][_DUMP]["byte"]), righe=trovate)


__all__ = ["PREFISSO", "TABELLE", "Snapshot", "esporta", "importa", "snapshot_completi"]
