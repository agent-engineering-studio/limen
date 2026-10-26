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
    _errori_non_ammessi,
    _esegui,
    _livello,
    _pg,
    _sha256,
)
from limen.data.object_store import ObjectStore
from limen.integrations.static_bootstrap.fingerprint import SOURCE as BOOTSTRAP_SOURCE

log = get_logger(__name__)

PREFISSO = "statico/"
TABELLE = ("public.cell_static_factors", "public.flood_hazard_subdiv")
_DUMP = "statico.dump"
_FORMATO_ISTANTE = "%Y-%m-%dT%H-%M-%SZ"


@dataclass(frozen=True, slots=True)
class Snapshot:
    chiave: str
    byte: int
    righe: dict[str, int]


async def _griglia(conn: asyncpg.Connection) -> dict[str, dict[str, Any]]:
    """Per AOI: quante celle e un'impronta dei loro id, nell'ordine degli id."""
    righe = await conn.fetch(
        """
        SELECT aoi_id, count(*) AS celle, md5(string_agg(id, ',' ORDER BY id)) AS impronta
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

    await conn.execute(f"TRUNCATE {', '.join(TABELLE)}")
    pg = _pg(cfg, dsn)
    _, err = await _esegui(
        pg(
            "pg_restore",
            "--data-only",
            "--single-transaction",
            "--no-owner",
            "--no-password",
            f"--dbname={pg.dsn}",
        ),
        env=pg.env,
        stdin=dump,
        errori_sql=True,
    )
    if cattivi := _errori_non_ammessi(err):
        raise BackupError(
            f"pg_restore: {'; '.join(cattivi[:5])} — le tabelle sono vuote, rilancia l'import"
        )
    trovate = await _conta(conn, list(TABELLE))
    attese: dict[str, int] = manifest["righe"]
    if trovate != attese:
        raise BackupError(f"righe diverse dallo snapshot: attese {attese}, trovate {trovate}")

    # Le impronte per ultime: registrate prima di avere i dati, un import
    # fallito lascerebbe il bootstrap convinto di non dover ricalcolare.
    await conn.executemany(
        """
        INSERT INTO dataset_versions (source, dataset, version, metadata)
        SELECT $1, $2, $3, $4::jsonb
         WHERE NOT EXISTS (
               SELECT 1 FROM dataset_versions
                WHERE source = $1 AND dataset = $2 AND version = $3)
        """,
        [
            (BOOTSTRAP_SOURCE, i["dataset"], i["version"], i["metadata"])
            for i in manifest["impronte"]
        ],
    )
    log.info(
        "static_snapshot.importato",
        chiave=chiave,
        righe=trovate,
        impronte=len(manifest["impronte"]),
        hint="poi limen calibrate: le statistiche per AOI non sono nello snapshot",
    )
    return Snapshot(chiave=chiave, byte=int(manifest["file"][_DUMP]["byte"]), righe=trovate)


__all__ = ["PREFISSO", "TABELLE", "Snapshot", "esporta", "importa", "snapshot_completi"]
