"""Idempotenza sul **costo** del bootstrap statico, non solo sul risultato (#101).

`bootstrap-static` era già idempotente nel risultato — rieseguirlo lasciava lo
stesso stato — ma ogni passo era un `UPDATE` su tutte le celle dell'AOI,
incondizionato. Sul DTM a 5 m sono ~2m45s ogni 11.000 celle, cioè un'ora e
mezza sulle 312.000 nazionali. È il motivo per cui il passo non stava dentro
`make up` e andava ricordato a mano — e un passo che va ricordato è un passo
che prima o poi non si esegue.

Qui il passo si salta quando la **sorgente non è cambiata**. Il meccanismo non
è nuovo: è l'invariante `Idempotency (sync jobs)` di `CLAUDE.md`, cioè
`dataset_versions(source, dataset, version)`. I job di sync la usavano già; il
bootstrap no.

Tre cose che l'impronta deve contenere, e il perché di ciascuna:

* **la sorgente** — mtime e dimensione per i file, conteggio e ultimo
  inserimento per le tabelle. Non l'hash del contenuto: su un mosaico DTM da
  gigabyte leggerlo per intero costerebbe quanto ricalcolare;
* **il numero di celle dell'AOI** — un re-seed che cambia la griglia deve
  invalidare tutto, perché i fattori sono per cella e le celle non sono più
  quelle;
* **una versione di codice per passo** (`STEP_VERSION`) — quando cambia la
  *formula* e non la sorgente, il risultato va rifatto. È successo davvero con
  la formula WUI della #62 e con `imperviousness_norm` della #63, e senza
  questa riga il bootstrap avrebbe risposto "invariato" a una domanda diversa.

La chiave è **(aoi_id, passo)** e non globale: aggiungere una regione deve
calcolare quella, non rifare le altre diciannove.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import dataset_versions_repo

log = get_logger(__name__)

#: Il `source` sotto cui il bootstrap registra le proprie versioni. Separato
#: da quelli dei job di sync, che registrano la versione del *dato scaricato*;
#: qui si registra la versione del *calcolo derivato*.
SOURCE = "static_bootstrap"

#: Versione del **codice** di ogni passo. Va incrementata quando cambia la
#: formula, non quando cambia la sorgente: è ciò che distingue "il dato è lo
#: stesso" da "il modo di leggerlo è lo stesso". Un passo assente da questa
#: mappa vale 1.
STEP_VERSION: dict[str, int] = {
    "geoserver_source": 1,
    "iffi": 1,
    "pai": 1,
    "flood_hazard": 1,
    "fire_density": 1,
    "fire_perimeters": 1,
    "osm_distance": 1,
    "dem": 1,
    "corine": 1,
    "wui": 1,
    "imperviousness": 1,
    "geological": 1,
}


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """Lo stato della sorgente di un passo, o il fatto che non ci sia.

    ``available=False`` non è un errore: è un passo la cui sorgente non è
    configurata su questo deployment, e resta uno skip pulito — l'invariante
    di degradazione del progetto applicata al bootstrap.
    """

    parts: tuple[str, ...] = ()
    available: bool = True
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def merge(self, other: Fingerprint) -> Fingerprint:
        """Unisci due impronte: indisponibile se lo è una delle due."""
        if not self.available:
            return self
        if not other.available:
            return other
        return Fingerprint(
            parts=self.parts + other.parts,
            details={**self.details, **other.details},
        )


def missing(reason: str) -> Fingerprint:
    """Sorgente non configurata: il passo si salta e lo dice."""
    return Fingerprint(available=False, reason=reason)


def of_env_file(env_var: str) -> Fingerprint:
    """Impronta di un file indicato da una variabile d'ambiente.

    ``(path, mtime_ns, size)``. L'mtime da solo non basta — copiare un file
    diverso con lo stesso timestamp è raro ma possibile — e l'hash del
    contenuto costa troppo su un raster da gigabyte. La dimensione chiude il
    caso pratico.

    La variabile arriva dalla costante esportata dal job che la legge
    (``DEM_RASTER_ENV`` e simili), non da una stringa riscritta qui: due nomi
    che devono coincidere e vivono in due file divergono al primo rinomino.
    """
    value = os.environ.get(env_var)
    if not value:
        return missing(f"{env_var} non impostata")
    path = Path(value)
    try:
        st = path.stat()
    except OSError:
        return missing(f"file assente: {path}")
    return Fingerprint(
        parts=(f"{path}:{st.st_mtime_ns}:{st.st_size}",),
        details={"path": str(path), "size": st.st_size},
    )


async def of_tables(*tables: str, require_rows: bool = True) -> Fingerprint:
    """Impronta di una o più tabelle sorgente: conteggio e ultimo inserimento.

    ``require_rows`` distingue due casi che sembrano uguali e non lo sono: una
    tabella **vuota** perché il dato non è stato ingerito (skip pulito) da una
    tabella vuota che è una risposta legittima — `fire_events` senza hotspot
    significa "nessun incendio", e la densità a zero è un'informazione.
    """
    parts: list[str] = []
    total = 0
    async with acquire() as conn:
        for table in tables:
            exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table}")
            if not exists:
                return missing(f"tabella assente: {table}")
            n = int(await conn.fetchval(f"SELECT count(*) FROM {table}") or 0)
            has_created = await conn.fetchval(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = 'created_at'",
                table,
            )
            last = (
                await conn.fetchval(f"SELECT max(created_at) FROM {table}") if has_created else None
            )
            parts.append(f"{table}:{n}:{last or '-'}")
            total += n
    if require_rows and total == 0:
        return missing(f"nessuna riga in {', '.join(tables)}")
    return Fingerprint(parts=tuple(parts), details={"rows": total})


@dataclass
class StepOutcome:
    """Cosa è successo a un passo, per la riga di riepilogo."""

    step: str
    ran: bool
    reason: str


class StepGate:
    """Decide quali passi rieseguire per un AOI, e tiene il conto.

    Uso::

        gate = await StepGate.create("it-puglia", force=False)
        if await gate.needs("dem", fingerprint.of_env_file(DEM_RASTER_ENV)):
            await sync_dem_for_aois(aoi_ids=["it-puglia"])
            await gate.done("dem")
    """

    def __init__(self, aoi_id: str, grid_cells: int, *, force: bool) -> None:
        self._aoi_id = aoi_id
        self._grid_cells = grid_cells
        self._force = force
        self._pending: dict[str, str] = {}
        self.outcomes: list[StepOutcome] = []

    @classmethod
    async def create(cls, aoi_id: str, *, force: bool = False) -> StepGate:
        async with acquire() as conn:
            cells = int(
                await conn.fetchval("SELECT count(*) FROM grid_cells WHERE aoi_id = $1", aoi_id)
                or 0
            )
        return cls(aoi_id, cells, force=force)

    def _version(self, step: str, fp: Fingerprint) -> str:
        payload = [
            # Il nome del passo dentro la versione, non solo nella chiave
            # `dataset`: due passi che leggono la stessa sorgente (CORINE e
            # WUI) altrimenti producono la stessa stringa, e in
            # `dataset_versions` si vedono due righe identiche che non si
            # distinguono a occhio.
            f"step={step}",
            f"step_version={STEP_VERSION.get(step, 1)}",
            f"grid_cells={self._grid_cells}",
            *fp.parts,
        ]
        return dataset_versions_repo.content_hash(payload)

    async def needs(self, step: str, fp: Fingerprint) -> bool:
        """True se il passo va eseguito. Registra l'esito per il riepilogo."""
        if not fp.available:
            log.info("static_bootstrap.skip", aoi_id=self._aoi_id, step=step, reason=fp.reason)
            self.outcomes.append(StepOutcome(step, ran=False, reason=fp.reason))
            return False

        version = self._version(step, fp)
        if self._force:
            self._pending[step] = version
            self.outcomes.append(StepOutcome(step, ran=True, reason="forzato"))
            return True

        dataset = f"{step}:{self._aoi_id}"
        seen = await dataset_versions_repo.find(SOURCE, dataset, version)
        if seen is not None:
            log.info(
                "static_bootstrap.unchanged", aoi_id=self._aoi_id, step=step, version=version[:12]
            )
            self.outcomes.append(StepOutcome(step, ran=False, reason="sorgente invariata"))
            return False

        self._pending[step] = version
        # Perché rieseguire: "mai calcolato" e "la sorgente è cambiata" portano
        # a domande diverse quando qualcuno guarda il log.
        prior = await _any_version_for(dataset)
        self.outcomes.append(
            StepOutcome(step, ran=True, reason="sorgente cambiata" if prior else "prima esecuzione")
        )
        return True

    async def done(self, step: str, **metadata: Any) -> None:
        """Registra che il passo è arrivato in fondo.

        Chiamata **dopo** il lavoro e non prima: un passo che esplode a metà
        non deve lasciare una versione che lo faccia saltare al giro dopo.
        """
        version = self._pending.pop(step, None)
        if version is None:
            return
        await dataset_versions_repo.record(
            source=SOURCE,
            dataset=f"{step}:{self._aoi_id}",
            version=version,
            metadata={"aoi_id": self._aoi_id, "grid_cells": self._grid_cells, **metadata},
        )

    def summary(self) -> str:
        """La riga che `make up` stampa: cosa ha saltato, e perché."""
        ran = [o for o in self.outcomes if o.ran]
        skipped = [o for o in self.outcomes if not o.ran]
        if not ran:
            return (
                f"{self._aoi_id}: {len(skipped)} passi saltati (sorgente invariata), 0 ricalcolati"
            )
        detail = ", ".join(f"{o.step}: {o.reason}" for o in ran)
        return f"{self._aoi_id}: {len(ran)} ricalcolati ({detail}), {len(skipped)} saltati"


async def _any_version_for(dataset: str) -> bool:
    """C'è già una versione registrata per questo passo, quale che sia?"""
    async with acquire() as conn:
        return bool(
            await conn.fetchval(
                "SELECT 1 FROM dataset_versions WHERE source = $1 AND dataset = $2 LIMIT 1",
                SOURCE,
                dataset,
            )
        )


__all__ = [
    "SOURCE",
    "STEP_VERSION",
    "Fingerprint",
    "StepGate",
    "StepOutcome",
    "missing",
    "of_env_file",
    "of_tables",
]
