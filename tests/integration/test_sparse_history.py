"""Lo storico registra i cambiamenti, non i fotogrammi (#135).

Lo sweep orario scriveva una riga per cella a ogni giro: ~19 milioni al
giorno, di cui la maggioranza identiche a quelle dell'ora prima. Il
2026-09-28 hanno riempito il volume e Postgres è andato in crash loop.

Lo stato corrente vive in `latest_risk` dal #125 ed è completo per
costruzione, quindi lo storico può permettersi di essere rado. Questi test
fissano le tre proprietà che rendono valido il cambio: la mappa resta
sempre aggiornata, lo storico cresce solo quando succede qualcosa, e una
cella immobile non sparisce.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shapely.geometry import Polygon

from limen.agents.executors.persist_result import PersistResultExecutor
from limen.core.models.context import (
    AggregateAssessment,
    CellRiskRecord,
    MonitoringContext,
)
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.grid_repo import generate_and_store_grid
from tests.factories import landslide_record

_AOI_ID = "it-test-135"
_AOI = Polygon([(16.80, 41.10), (16.83, 41.10), (16.83, 41.13), (16.80, 41.13)])


async def _seed_cells() -> list[str]:
    await upsert_aoi(id=_AOI_ID, name="sparse history", kind="test", geom=_AOI)
    await generate_and_store_grid(_AOI_ID)
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM grid_cells WHERE aoi_id = $1 ORDER BY id LIMIT 3",
            _AOI_ID,
        )
    return [str(r["id"]) for r in rows]


def _ctx(cells: list[CellRiskRecord]) -> MonitoringContext:
    momento = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    return MonitoringContext(
        aoi_id=_AOI_ID,
        valuation_time=momento,
        cell_ids=tuple(c.cell_id for c in cells),
        cell_results=cells,
        assessment=AggregateAssessment(
            aoi_id=_AOI_ID,
            model_version="limen-deterministic-v1",
            valuation_time=momento,
            n_cells=len(cells),
            cells_high_or_above=0,
            cells_by_level={},
            top_cells=cells,
        ),
    )


async def _persist(cells: list[CellRiskRecord], **kw: float | int) -> None:
    await PersistResultExecutor(**kw).run(_ctx(cells))  # type: ignore[arg-type]


async def _conta() -> tuple[int, int]:
    async with acquire() as conn:
        storico = await conn.fetchval(
            "SELECT count(*) FROM risk_assessments ra "
            "JOIN grid_cells g ON g.id = ra.cell_id WHERE g.aoi_id = $1",
            _AOI_ID,
        )
        corrente = await conn.fetchval(
            "SELECT count(*) FROM latest_risk lr "
            "JOIN grid_cells g ON g.id = lr.cell_id WHERE g.aoi_id = $1",
            _AOI_ID,
        )
    return int(storico), int(corrente)


async def test_uno_sweep_identico_non_riscrive_lo_storico(reset_db: None, pg_pool: object) -> None:
    ids = await _seed_cells()
    celle = [landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids]

    await _persist(celle)
    dopo_uno = await _conta()
    assert dopo_uno == (len(ids), len(ids))

    # Stesso punteggio, stessa classe: non è una notizia.
    await _persist(celle)
    storico, corrente = await _conta()
    assert storico == len(ids), "lo storico è raddoppiato: la scrittura selettiva non funziona"
    assert corrente == len(ids)


async def test_la_mappa_resta_aggiornata_anche_senza_riga_di_storico(
    reset_db: None, pg_pool: object
) -> None:
    # Il punto delicato: saltare lo storico non deve far invecchiare lo
    # stato corrente, che è quello che la mappa disegna.
    ids = await _seed_cells()
    await _persist([landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids])
    async with acquire() as conn:
        primo = await conn.fetchval(
            "SELECT max(computed_at) FROM latest_risk WHERE cell_id = ANY($1::text[])", ids
        )
    await _persist([landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids])
    async with acquire() as conn:
        secondo, storia = await conn.fetchrow(  # type: ignore[misc]
            "SELECT max(computed_at), max(history_at) FROM latest_risk "
            "WHERE cell_id = ANY($1::text[])",
            ids,
        )
    assert secondo > primo, "lo stato corrente non è avanzato"
    assert storia < secondo, "history_at è avanzato senza che sia stata scritta una riga"


async def test_un_cambio_di_classe_è_sempre_una_notizia(reset_db: None, pg_pool: object) -> None:
    ids = await _seed_cells()
    await _persist([landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids])
    prima, _ = await _conta()

    # Punteggio poco diverso ma classe diversa: la soglia sullo scostamento
    # non deve poter nascondere un salto di classe, che è la cosa che un
    # operatore legge.
    await _persist(
        [landslide_record(ids[0], score=0.11, level=RiskLevel.Low)]
        + [landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids[1:]]
    )
    dopo, _ = await _conta()
    assert dopo == prima + 1


async def test_uno_scostamento_oltre_la_soglia_è_una_notizia(
    reset_db: None, pg_pool: object
) -> None:
    ids = await _seed_cells()
    await _persist([landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids])
    prima, _ = await _conta()
    # Stessa classe, punteggio ben oltre la soglia di 0,02.
    await _persist(
        [landslide_record(c, score=0.14, level=RiskLevel.None_) for c in ids],
        history_min_delta=0.02,
    )
    dopo, _ = await _conta()
    assert dopo == prima + len(ids)


async def test_il_battito_lascia_una_traccia_anche_se_non_cambia_nulla(
    reset_db: None, pg_pool: object
) -> None:
    # Senza battito la retention farebbe scadere l'ultima riga di una cella
    # immobile e la sua storia si azzererebbe: il trend mostrerebbe il vuoto
    # dove c'è la calma.
    ids = await _seed_cells()
    celle = [landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids]
    await _persist(celle)
    prima, _ = await _conta()

    async with acquire() as conn:
        await conn.execute(
            "UPDATE latest_risk SET history_at = history_at - interval '2 days' "
            "WHERE cell_id = ANY($1::text[])",
            ids,
        )
    await _persist(celle, history_heartbeat_hours=24)
    dopo, _ = await _conta()
    assert dopo == prima + len(ids)


async def test_con_delta_zero_si_torna_a_scrivere_sempre(reset_db: None, pg_pool: object) -> None:
    # La via d'uscita: `history_min_delta=0` riproduce il comportamento
    # precedente, che è ciò che serve se un giorno lo storico completo
    # dovesse tornare a servire.
    ids = await _seed_cells()
    celle = [landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids]
    await _persist(celle, history_min_delta=0.0)
    await _persist(celle, history_min_delta=0.0)
    storico, _ = await _conta()
    assert storico == 2 * len(ids)


@pytest.mark.parametrize("delta", [0.0, 0.5])
async def test_lo_stato_corrente_è_sempre_completo(
    reset_db: None, pg_pool: object, delta: float
) -> None:
    # Qualunque sia la soglia, `latest_risk` ha una riga per cella: è
    # l'invariante su cui poggiano la mappa e tutte le API dal #125.
    ids = await _seed_cells()
    await _persist(
        [landslide_record(c, score=0.10, level=RiskLevel.None_) for c in ids],
        history_min_delta=delta,
    )
    _, corrente = await _conta()
    assert corrente == len(ids)
