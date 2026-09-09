"""Truth set alluvione e maschere di osservazione (issue #64).

Le parti che vivono nel database, contro un Postgres vero: che la verità sia
l'intersezione geometrica col perimetro **osservato** e non l'area mappata,
che una cella allagata due volte conti una volta, e che la maschera dica
quando quella cella è stata guardata — la differenza fra un falso allarme e
un allarme senza risposta.

Il ground truth qui è inserito a mano nelle stesse tabelle che popola
l'ingest, così ciò che si prova è la logica che girerà sui dati veri.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shapely.geometry import box

from limen.data.db import acquire
from limen.data.repos.flood_events_repo import (
    activations_summary,
    catalogue_window,
    count_events,
    observation_times,
    truth_cells,
    upsert_many,
    upsert_masks,
)
from limen.integrations.copernicus_ems.client import ObservationMask, ObservedFlood

pytestmark = pytest.mark.integration

AOI = "bt-flood"
EVENT = datetime(2024, 9, 18, 6, tzinfo=UTC)
PASS_OVER = datetime(2024, 9, 20, 5, 27, tzinfo=UTC)


async def _seed_grid() -> None:
    """Tre celle in fila: la prima si allaga, la seconda è osservata e resta
    asciutta, la terza nessuno la guarda."""
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'BT flood','region',"
            "ST_Multi(ST_MakeEnvelope(11.0, 44.0, 11.4, 44.2, 4326)))",
            AOI,
        )
        for i in range(3):
            x = 11.0 + i * 0.1
            await conn.execute(
                "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) "
                "VALUES ($1,$2,0,$3, ST_MakeEnvelope($4,44.0,$5,44.1,4326), 1.0)",
                f"{AOI}|0|{i}",
                AOI,
                i,
                x,
                x + 0.1,
            )


def _flood(cell_index: int, *, event_id: str, when: datetime = EVENT) -> ObservedFlood:
    x = 11.0 + cell_index * 0.1
    return ObservedFlood(
        id=event_id,
        activation_code="EMSR762",
        aoi_label="AOI01",
        event_time=when,
        geom=box(x + 0.01, 44.01, x + 0.05, 44.05),
        area_km2=1.2,
        observed_time=PASS_OVER,
        event_type="Riverine flood",
        detection_method="Semi-automatic extraction",
        attributes={"notation": "Flooded area", "activation_name": "Flood in Test"},
    )


def _mask(*, mask_id: str = "EMSR762-aoi01-DEL0") -> ObservationMask:
    """Copre le prime due celle, non la terza."""
    return ObservationMask(
        id=mask_id,
        activation_code="EMSR762",
        aoi_label="AOI01",
        product_type="DEL",
        observed_time=PASS_OVER,
        # Fino a 11,19 e non a 11,2: un bordo condiviso è
        # un'intersezione, e la terza cella comincia esattamente lì.
        geom=box(11.0, 44.0, 11.19, 44.1),
        area_km2=200.0,
    )


async def test_truth_is_the_observed_perimeter_not_the_mapped_area(
    reset_db: None, pg_pool: object
) -> None:
    """La cella osservata e asciutta non è verità: è il denominatore del FAR."""
    await _seed_grid()
    await upsert_many([_flood(0, event_id="e1")])
    await upsert_masks([_mask()])

    truth = await truth_cells(
        AOI, start=datetime(2024, 1, 1, tzinfo=UTC), end=datetime(2025, 1, 1, tzinfo=UTC)
    )

    assert set(truth) == {f"{AOI}|0|0"}
    assert truth[f"{AOI}|0|0"] == EVENT


async def test_a_cell_flooded_twice_counts_once(reset_db: None, pg_pool: object) -> None:
    """Altrimenti un'area ben allertata gonfierebbe l'hit rate quante volte
    si è allagata."""
    await _seed_grid()
    later = datetime(2024, 10, 20, 6, tzinfo=UTC)
    await upsert_many([_flood(0, event_id="e1"), _flood(0, event_id="e2", when=later)])

    truth = await truth_cells(
        AOI, start=datetime(2024, 1, 1, tzinfo=UTC), end=datetime(2025, 1, 1, tzinfo=UTC)
    )

    assert len(truth) == 1
    # L'ancora è il **primo** evento: la domanda è se l'allerta è arrivata
    # prima dell'acqua, e la seconda alluvione non sposta quella soglia.
    assert truth[f"{AOI}|0|0"] == EVENT


async def test_events_outside_the_window_are_not_truth(reset_db: None, pg_pool: object) -> None:
    await _seed_grid()
    await upsert_many([_flood(0, event_id="e1")])

    truth = await truth_cells(
        AOI, start=datetime(2025, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert truth == {}


async def test_observation_mask_says_which_cells_were_looked_at(
    reset_db: None, pg_pool: object
) -> None:
    """Le prime due celle sì, la terza no — ed è ciò che separa un falso
    allarme da un allarme senza risposta."""
    await _seed_grid()
    await upsert_masks([_mask()])

    observed = await observation_times(AOI)

    assert set(observed) == {f"{AOI}|0|0", f"{AOI}|0|1"}
    assert observed[f"{AOI}|0|1"] == [PASS_OVER]


async def test_two_passes_over_the_same_cell_are_two_observations(
    reset_db: None, pg_pool: object
) -> None:
    """Una AOI monitorata due volte è stata guardata due volte, e un'allerta
    è verificabile solo rispetto a un passaggio venuto dopo di essa."""
    await _seed_grid()
    second = datetime(2024, 9, 22, 5, tzinfo=UTC)
    await upsert_masks(
        [
            _mask(),
            ObservationMask(
                id="EMSR762-aoi01-DEL1",
                activation_code="EMSR762",
                aoi_label="AOI01",
                product_type="DEL",
                observed_time=second,
                geom=box(11.0, 44.0, 11.19, 44.1),
            ),
        ]
    )

    observed = await observation_times(AOI)

    assert observed[f"{AOI}|0|0"] == [PASS_OVER, second]


async def test_upsert_is_idempotent(reset_db: None, pg_pool: object) -> None:
    await _seed_grid()
    await upsert_many([_flood(0, event_id="e1")])
    await upsert_many([_flood(0, event_id="e1")])
    await upsert_masks([_mask()])
    await upsert_masks([_mask()])

    assert await count_events() == 1
    async with acquire() as conn:
        masks = await conn.fetchval("SELECT count(*) FROM flood_observation_masks")
    assert int(masks) == 1


async def test_provenance_summary_reports_source_coverage(reset_db: None, pg_pool: object) -> None:
    """Il report deve poter dire fonte, data e area senza rifare i conti."""
    await _seed_grid()
    await upsert_many([_flood(0, event_id="e1"), _flood(1, event_id="e2")])

    rows = await activations_summary()
    lo, hi = await catalogue_window()

    assert len(rows) == 1
    assert rows[0].activation_code == "EMSR762"
    assert rows[0].polygons == 2
    assert rows[0].area_km2 == pytest.approx(2.4)
    assert (lo, hi) == (EVENT, EVENT)
