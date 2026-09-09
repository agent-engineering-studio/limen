"""Severità per perimetro dal FRP degli hotspot (issue #67).

Il calcolo è set-based in SQL, quindi si prova contro un Postgres vero. Le
proprietà che contano sono quelle in cui è facile sbagliare in silenzio:

* solo gli hotspot **dentro** il perimetro e **in finestra** contribuiscono;
* solo quelli di vegetazione — un'acciaieria dentro il perimetro sommerebbe
  potenza che non viene da quel rogo;
* la densità è la somma divisa per l'area, quindi due incendi con la stessa
  energia totale ma aree diverse hanno severità diverse;
* un'area assente o nulla lascia la densità a NULL invece di dividere per zero.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.data.db import acquire
from limen.data.repos.fire_events_repo import (
    frp_size_correlation,
    perimeter_severity_at,
    refresh_perimeter_frp,
)
from limen.data.repos.fire_repo import FireHotspot, upsert_hotspots

pytestmark = pytest.mark.integration

AOI = "bt-severity"
FIRE_DAY = dt.date(2024, 8, 1)


async def _seed_aoi() -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'BT sev','region',"
            "ST_Multi(ST_MakeEnvelope(16.0, 40.9, 16.6, 41.2, 4326)))",
            AOI,
        )


async def _perimeter(
    perimeter_id: str, *, west: float, area_ha: float | None, day: dt.date = FIRE_DAY
) -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO fire_perimeters (id, fire_date, area_ha, geom) VALUES ($1,$2,$3,"
            "ST_Multi(ST_MakeEnvelope($4,41.0,$5,41.05,4326)))",
            perimeter_id,
            day,
            area_ha,
            west,
            west + 0.05,
        )


def _hotspot(
    *,
    lon: float,
    day: dt.date = FIRE_DAY,
    time_hhmm: int = 1130,
    frp: float = 100.0,
    detection_type: int | None = 0,
) -> FireHotspot:
    return FireHotspot(
        source="VIIRS_SNPP_SP",
        acq_date=day,
        acq_time=time_hhmm,
        latitude=41.02,
        longitude=lon,
        frp_mw=frp,
        confidence="h",
        detection_type=detection_type,
    )


async def _density(perimeter_id: str) -> float | None:
    async with acquire() as conn:
        return await conn.fetchval(
            "SELECT frp_density_mw_per_ha FROM fire_perimeters WHERE id = $1", perimeter_id
        )


async def test_only_hotspots_inside_the_perimeter_contribute(
    reset_db: None, pg_pool: object
) -> None:
    await _seed_aoi()
    await _perimeter("p1", west=16.01, area_ha=100.0)
    await upsert_hotspots(
        [
            _hotspot(lon=16.03, frp=100.0),  # dentro
            _hotspot(lon=16.50, frp=900.0, time_hhmm=1200),  # fuori
        ]
    )

    await refresh_perimeter_frp()

    assert await _density("p1") == pytest.approx(1.0)


async def test_only_hotspots_inside_the_window_contribute(reset_db: None, pg_pool: object) -> None:
    """La firedate EFFIS è l'inizio, gli hotspot sono orbite: la finestra
    copre la durata tipica senza raccogliere l'incendio successivo."""
    await _seed_aoi()
    await _perimeter("p1", west=16.01, area_ha=100.0)
    await upsert_hotspots(
        [
            _hotspot(lon=16.03, day=FIRE_DAY + dt.timedelta(days=2), frp=100.0),
            _hotspot(lon=16.03, day=FIRE_DAY + dt.timedelta(days=40), frp=900.0),
        ]
    )

    await refresh_perimeter_frp()

    assert await _density("p1") == pytest.approx(1.0)


async def test_an_industrial_source_inside_the_perimeter_is_excluded(
    reset_db: None, pg_pool: object
) -> None:
    """Sommerebbe potenza radiativa che non viene da quel rogo."""
    await _seed_aoi()
    await _perimeter("p1", west=16.01, area_ha=100.0)
    await upsert_hotspots(
        [
            _hotspot(lon=16.03, frp=100.0, detection_type=0),
            _hotspot(lon=16.04, frp=5000.0, detection_type=2, time_hhmm=1200),
        ]
    )

    await refresh_perimeter_frp()

    assert await _density("p1") == pytest.approx(1.0)


async def test_density_separates_intensity_from_size(reset_db: None, pg_pool: object) -> None:
    """Il motivo per cui non si usa la somma di FRP.

    Due incendi con la **stessa energia totale** ma aree diverse: la somma li
    dichiarerebbe uguali, la densità dice che il piccolo ha bruciato dieci
    volte più intensamente.
    """
    await _seed_aoi()
    await _perimeter("piccolo", west=16.01, area_ha=100.0)
    await _perimeter("grande", west=16.21, area_ha=1000.0)
    await upsert_hotspots(
        [
            _hotspot(lon=16.03, frp=500.0),
            _hotspot(lon=16.23, frp=500.0, time_hhmm=1200),
        ]
    )

    await refresh_perimeter_frp()

    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, frp_sum_mw, frp_density_mw_per_ha FROM fire_perimeters ORDER BY id"
        )
    by_id = {str(r["id"]): r for r in rows}
    assert by_id["piccolo"]["frp_sum_mw"] == by_id["grande"]["frp_sum_mw"]
    assert float(by_id["piccolo"]["frp_density_mw_per_ha"]) == pytest.approx(5.0)
    assert float(by_id["grande"]["frp_density_mw_per_ha"]) == pytest.approx(0.5)


async def test_missing_area_leaves_density_null(reset_db: None, pg_pool: object) -> None:
    """NULL è "non misurabile", che è la cosa giusta da propagare al motore —
    e non una divisione per zero."""
    await _seed_aoi()
    await _perimeter("senza_area", west=16.01, area_ha=None)
    await _perimeter("area_zero", west=16.21, area_ha=0.0)
    await upsert_hotspots(
        [_hotspot(lon=16.03, frp=100.0), _hotspot(lon=16.23, frp=100.0, time_hhmm=1200)]
    )

    await refresh_perimeter_frp()

    assert await _density("senza_area") is None
    assert await _density("area_zero") is None


async def test_refresh_is_idempotent(reset_db: None, pg_pool: object) -> None:
    await _seed_aoi()
    await _perimeter("p1", west=16.01, area_ha=100.0)
    await upsert_hotspots([_hotspot(lon=16.03, frp=100.0)])

    await refresh_perimeter_frp()
    first = await _density("p1")
    await refresh_perimeter_frp()

    assert await _density("p1") == first


async def test_the_executor_reads_the_most_recent_measurable_perimeter(
    reset_db: None, pg_pool: object
) -> None:
    """Un perimetro più recente ma non misurabile non deve nascondere quello
    prima: il motore riceverebbe `None` e perderebbe una severità che c'è."""
    await _seed_aoi()
    await _perimeter("vecchio", west=16.01, area_ha=100.0, day=FIRE_DAY)
    await _perimeter(
        "recente_senza_area", west=16.21, area_ha=None, day=FIRE_DAY + dt.timedelta(days=10)
    )
    await upsert_hotspots(
        [_hotspot(lon=16.03, frp=100.0), _hotspot(lon=16.23, frp=100.0, time_hhmm=1200)]
    )
    await refresh_perimeter_frp()

    density = await perimeter_severity_at(AOI, on_or_before=FIRE_DAY + dt.timedelta(days=30))

    assert density == pytest.approx(1.0)


async def test_correlation_report_needs_positive_areas(reset_db: None, pg_pool: object) -> None:
    """Il controllo di sanità non deve inventare correlazioni su un campione
    vuoto."""
    await _seed_aoi()

    out = await frp_size_correlation()

    assert out["perimeters"] == 0
