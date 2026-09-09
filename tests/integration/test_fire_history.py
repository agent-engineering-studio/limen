"""Eventi incendio per cella-giorno e densità storica (issue #66).

Le parti che vivono nel database. Quattro proprietà, tutte imparate a spese
di un giro sbagliato sui dati veri:

* solo il tipo 0 diventa evento — altrimenti la cella più "incendiata"
  d'Italia è l'ILVA di Taranto;
* i passaggi multipli dello stesso rogo nello stesso giorno sono **un** evento;
* la ricostruzione è deterministica e rieseguibile, e una detection ritirata
  spa­risce invece di restare per sempre;
* `fire_density` è 0 e non NULL dove non è mai bruciato, perché lo zero è
  un'informazione mentre NULL vorrebbe dire "layer non caricato".
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.data.db import acquire
from limen.data.repos.fire_events_repo import (
    count_events,
    effis_firms_agreement,
    events_for_cells,
    rebuild_events,
    refresh_density,
)
from limen.data.repos.fire_repo import FireHotspot, upsert_hotspots

pytestmark = pytest.mark.integration

AOI = "bt-fire-history"
DAY = dt.date(2024, 8, 1)
WINDOW = (dt.date(2024, 1, 1), dt.date(2024, 12, 31))


async def _seed_grid(cells: int = 3) -> None:
    """Celle in fila lungo 16.0-16.3 E, tutte a cavallo di 41.0 N."""
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'BT storia','region',"
            "ST_Multi(ST_MakeEnvelope(16.0, 40.9, 16.4, 41.1, 4326)))",
            AOI,
        )
        for i in range(cells):
            x = 16.0 + i * 0.1
            await conn.execute(
                "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) "
                "VALUES ($1,$2,0,$3, ST_MakeEnvelope($4,41.0,$5,41.05,4326), 1.0)",
                f"{AOI}|0|{i}",
                AOI,
                i,
                x,
                x + 0.1,
            )
            await conn.execute(
                "INSERT INTO cell_static_factors (cell_id) VALUES ($1)", f"{AOI}|0|{i}"
            )


def _hotspot(
    *,
    cell_index: int,
    day: dt.date = DAY,
    time_hhmm: int = 1130,
    detection_type: int | None = 0,
    source: str = "VIIRS_SNPP_SP",
    frp: float = 12.5,
) -> FireHotspot:
    return FireHotspot(
        source=source,
        acq_date=day,
        acq_time=time_hhmm,
        latitude=41.02,
        longitude=16.05 + cell_index * 0.1,
        frp_mw=frp,
        confidence="h",
        brightness_k=330.0,
        daynight="D",
        satellite="N",
        instrument="VIIRS",
        detection_type=detection_type,
    )


async def test_only_vegetation_detections_become_events(reset_db: None, pg_pool: object) -> None:
    """Il difetto che dava 3.308 giorni-incendio all'acciaieria di Taranto."""
    await _seed_grid()
    await upsert_hotspots(
        [
            _hotspot(cell_index=0, detection_type=0),
            _hotspot(cell_index=1, detection_type=2),  # impianto industriale
            _hotspot(cell_index=2, detection_type=1),  # vulcano
        ]
    )

    await rebuild_events(start=WINDOW[0], end=WINDOW[1])
    truth = await events_for_cells(AOI, start=WINDOW[0], end=WINDOW[1])

    assert set(truth) == {f"{AOI}|0|0"}


async def test_a_detection_of_unknown_class_is_not_an_event(
    reset_db: None, pg_pool: object
) -> None:
    """`None` tiene fuori: meglio perdere un giorno che rimettere un forno."""
    await _seed_grid()
    await upsert_hotspots([_hotspot(cell_index=0, detection_type=None)])

    await rebuild_events(start=WINDOW[0], end=WINDOW[1])

    assert await count_events() == 0


async def test_many_passes_over_one_fire_are_one_event(reset_db: None, pg_pool: object) -> None:
    """Un rogo produce decine di pixel caldi da più orbite e più satelliti.

    Contarli come eventi darebbe alla cella ben osservata la densità di dieci
    incendi.
    """
    await _seed_grid()
    await upsert_hotspots(
        [
            _hotspot(cell_index=0, time_hhmm=1130),
            _hotspot(cell_index=0, time_hhmm=1310, frp=40.0),
            _hotspot(cell_index=0, time_hhmm=2250, source="MODIS_SP"),
        ]
    )

    await rebuild_events(start=WINDOW[0], end=WINDOW[1])

    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT hotspots, sources, max_frp_mw FROM fire_events WHERE cell_id = $1",
            f"{AOI}|0|0",
        )
    assert await count_events() == 1
    assert int(row["hotspots"]) == 3
    # Le sorgenti restano tracciate: serve a sapere chi l'ha visto.
    assert sorted(row["sources"]) == ["MODIS_SP", "VIIRS_SNPP_SP"]
    assert float(row["max_frp_mw"]) == 40.0


async def test_a_fire_burning_three_days_is_three_events(reset_db: None, pg_pool: object) -> None:
    """Per il rischio è la cosa giusta: tre giorni di fuoco sono tre giorni in
    cui quella cella era in pericolo. L'ancora del truth set resta il primo."""
    await _seed_grid()
    days = [DAY, DAY + dt.timedelta(days=1), DAY + dt.timedelta(days=2)]
    await upsert_hotspots([_hotspot(cell_index=0, day=d) for d in days])

    await rebuild_events(start=WINDOW[0], end=WINDOW[1])
    truth = await events_for_cells(AOI, start=WINDOW[0], end=WINDOW[1])

    assert await count_events() == 3
    assert truth[f"{AOI}|0|0"] == DAY


async def test_rebuild_is_deterministic_and_forgets_withdrawn_detections(
    reset_db: None, pg_pool: object
) -> None:
    """Stessi input ⇒ stessi eventi; e una detection rimossa deve sparire.

    È il motivo per cui la ricostruzione è DELETE + INSERT sulla finestra e
    non un upsert: un upsert lascerebbe l'evento vecchio in tabella per
    sempre.
    """
    await _seed_grid()
    await upsert_hotspots([_hotspot(cell_index=0), _hotspot(cell_index=1)])

    first = await rebuild_events(start=WINDOW[0], end=WINDOW[1])
    second = await rebuild_events(start=WINDOW[0], end=WINDOW[1])
    assert (first, second) == (2, 2)

    async with acquire() as conn:
        await conn.execute("DELETE FROM fire_hotspots WHERE longitude > 16.1")
    await rebuild_events(start=WINDOW[0], end=WINDOW[1])

    assert await count_events() == 1


async def test_density_is_zero_not_null_where_nothing_ever_burned(
    reset_db: None, pg_pool: object
) -> None:
    """Lo zero è un'informazione; NULL vorrebbe dire "layer non caricato"."""
    await _seed_grid()
    await upsert_hotspots(
        [_hotspot(cell_index=0), _hotspot(cell_index=0, day=DAY + dt.timedelta(days=5))]
    )
    await rebuild_events(start=WINDOW[0], end=WINDOW[1])

    await refresh_density(AOI, start=WINDOW[0], end=WINDOW[1])

    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT cell_id, fire_density FROM cell_static_factors "
            "WHERE cell_id LIKE $1 ORDER BY cell_id",
            f"{AOI}|%",
        )
    density = {str(r["cell_id"]): r["fire_density"] for r in rows}
    assert density[f"{AOI}|0|0"] == 2
    assert density[f"{AOI}|0|1"] == 0
    assert all(v is not None for v in density.values())


async def test_density_refresh_is_idempotent(reset_db: None, pg_pool: object) -> None:
    await _seed_grid()
    await upsert_hotspots([_hotspot(cell_index=0)])
    await rebuild_events(start=WINDOW[0], end=WINDOW[1])

    await refresh_density(AOI, start=WINDOW[0], end=WINDOW[1])
    await refresh_density(AOI, start=WINDOW[0], end=WINDOW[1])

    async with acquire() as conn:
        value = await conn.fetchval(
            "SELECT fire_density FROM cell_static_factors WHERE cell_id = $1",
            f"{AOI}|0|0",
        )
    assert int(value) == 1


async def test_effis_agreement_matches_a_perimeter_with_a_nearby_hotspot(
    reset_db: None, pg_pool: object
) -> None:
    """Il controllo di sanità: due dataset indipendenti che si confermano.

    Un hotspot industriale vicino allo stesso perimetro non deve farlo
    passare: sarebbe un accordo comprato con una detection che non è un rogo.
    """
    await _seed_grid()
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO fire_perimeters (id, fire_date, geom) VALUES ('p1',$1,"
            "ST_Multi(ST_MakeEnvelope(16.04,41.01,16.07,41.03,4326)))",
            DAY,
        )
        await conn.execute(
            "INSERT INTO fire_perimeters (id, fire_date, geom) VALUES ('p2',$1,"
            "ST_Multi(ST_MakeEnvelope(16.24,41.01,16.27,41.03,4326)))",
            DAY,
        )
    await upsert_hotspots(
        [
            _hotspot(cell_index=0, detection_type=0),
            _hotspot(cell_index=2, detection_type=2),
        ]
    )

    out = await effis_firms_agreement(start=WINDOW[0], end=WINDOW[1])

    assert out == {"perimeters": 2, "matched": 1}
