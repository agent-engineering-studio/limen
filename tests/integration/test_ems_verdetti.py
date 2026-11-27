"""Vaglio radar delle mappe EMS nel database (#713).

Le parti che vivono in SQL: l'upsert rieseguibile delle tre tabelle, che le
celle «solide» vengano solo da mappe indipendenti, la verità per prodotto e il
riepilogo per attivazione che non somma i prodotti di monitoraggio.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shapely.geometry import MultiPolygon, box

from limen.data.db import acquire
from limen.data.repos import ems_verdetti_repo
from limen.data.repos.flood_events_repo import (
    activations_summary,
    observation_times_per_maschera,
    truth_cells_per_prodotto,
    upsert_many,
    upsert_masks,
)
from limen.integrations.copernicus_ems.client import ObservationMask, ObservedFlood
from limen.integrations.copernicus_ems.verdetti import (
    CONFERMATA,
    POSSIBILE,
    Accordo,
    Classe,
    Qualita,
    Rapporto,
)

pytestmark = pytest.mark.integration

AOI = "bt-ems"
EVENT = datetime(2023, 5, 16, 6, tzinfo=UTC)
PASS_OVER = datetime(2023, 5, 17, 10, tzinfo=UTC)


async def _seed_grid() -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'BT ems','region',"
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


def _flood(cell: int, event_id: str, area: float) -> ObservedFlood:
    x = 11.0 + cell * 0.1
    return ObservedFlood(
        id=event_id,
        activation_code="EMSR664",
        aoi_label="AOI01",
        event_time=EVENT,
        geom=box(x + 0.01, 44.01, x + 0.05, 44.05),
        area_km2=area,
        observed_time=PASS_OVER,
    )


def _rapporto(product: str, mask: str, *, independent: bool, cell: int) -> Rapporto:
    x = 11.0 + cell * 0.1
    zona = MultiPolygon([box(x + 0.02, 44.02, x + 0.03, 44.03)])
    stem = f"{product}_40m_x"
    return Rapporto(
        activation_code="EMSR664",
        product=product,
        mask_id=mask,
        stem=stem,
        qualita=Qualita(
            activation_code="EMSR664",
            product=product,
            stem=stem,
            verdict="to check",
            reason=None,
            flags=[{"code": "much_unmapped"}],
            measurements={"mapped_km2": 1.0},
            thresholds=None,
            gap_hours=1.0,
            resolution_m=40.0,
            file=f"{stem}_quality.json",
        ),
        accordo=Accordo(
            activation_code="EMSR664",
            product=product,
            stem=stem,
            computed=True,
            reason=None,
            independent=independent,
            km2={"confirmed": 0.1},
            scores={"csi": None},
            quality_verdict="to check",
            gap_hours=1.0,
            resolution_m=40.0,
            file=f"{stem}_agreement.json",
            geojson=f"{stem}_agreement.geojson",
        ),
        classi={
            CONFERMATA: Classe(CONFERMATA, 0.1, zona),
            POSSIBILE: Classe(POSSIBILE, 3.0, zona),
        },
    )


async def test_upsert_is_rerunnable_and_confirmed_cells_need_independence(
    reset_db: None, pg_pool: object
) -> None:
    await _seed_grid()
    rapporti = [
        _rapporto("AOI01_GRA_PRODUCT", "EMSR664-aoi01-GRA0", independent=True, cell=0),
        _rapporto("AOI01_DEL_PRODUCT", "EMSR664-aoi01-DEL0", independent=False, cell=1),
    ]
    assert await ems_verdetti_repo.upsert_many(rapporti) == 2
    assert await ems_verdetti_repo.upsert_many(rapporti) == 2

    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM ems_verdetti") == 2
        assert await conn.fetchval("SELECT count(*) FROM ems_acqua_possibile") == 2
        assert await conn.fetchval("SELECT count(*) FROM ems_acqua_confermata") == 2

    assert await ems_verdetti_repo.celle_confermate(AOI) == {f"{AOI}|0|0": {"EMSR664-aoi01-GRA0"}}
    verdetti = await ems_verdetti_repo.per_backtest()
    assert {v.mask_id: v.flag_codes for v in verdetti} == {
        "EMSR664-aoi01-GRA0": ("much_unmapped",),
        "EMSR664-aoi01-DEL0": ("much_unmapped",),
    }

    # Il rapporto di DEL0 sparisce dal disco: il suo verdetto non resta.
    await ems_verdetti_repo.upsert_many(rapporti[:1])
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM ems_verdetti") == 1
        assert await conn.fetchval("SELECT count(*) FROM ems_acqua_possibile") == 1
        assert await conn.fetchval("SELECT count(*) FROM ems_acqua_confermata") == 1


async def test_truth_and_passes_keep_the_product(reset_db: None, pg_pool: object) -> None:
    await _seed_grid()
    await upsert_many(
        [
            _flood(0, "EMSR664-aoi01-DEL0-0-0", 1.0),
            _flood(0, "EMSR664-aoi01-DEL1-0-0", 1.5),
            _flood(1, "EMSR664-aoi01-DEL1-1-0", 0.5),
        ]
    )
    await upsert_masks(
        [
            ObservationMask(
                id="EMSR664-aoi01-DEL1",
                activation_code="EMSR664",
                aoi_label="AOI01",
                product_type="DEL",
                observed_time=PASS_OVER,
                geom=box(11.0, 44.0, 11.19, 44.1),
            )
        ]
    )

    per_prodotto = await truth_cells_per_prodotto(
        AOI, start=datetime(2023, 1, 1, tzinfo=UTC), end=datetime(2024, 1, 1, tzinfo=UTC)
    )
    assert per_prodotto == {
        f"{AOI}|0|0": {"EMSR664-aoi01-DEL0": EVENT, "EMSR664-aoi01-DEL1": EVENT},
        f"{AOI}|0|1": {"EMSR664-aoi01-DEL1": EVENT},
    }
    passaggi = await observation_times_per_maschera(AOI)
    assert passaggi[f"{AOI}|0|0"] == [("EMSR664-aoi01-DEL1", PASS_OVER)]
    assert await ems_verdetti_repo.prodotti_ems() == {"EMSR664-aoi01-DEL0", "EMSR664-aoi01-DEL1"}

    # DEL0 e DEL1 sono la stessa AOI in due giorni: l'area è quella del più
    # esteso (2,0 km²), non la somma (3,0).
    (riga,) = await activations_summary()
    assert riga.polygons == 3
    assert riga.area_km2 == pytest.approx(2.0)
