"""`carica_vettori` contro un PostgreSQL vero (#426).

Il punto non è solo che le tabelle esistano: devono avere i nomi, le chiavi
e la geometria che mcp-geo-server dava loro, perché il loader, `seed-comuni`
e il lookup dei comuni le leggono per nome — e gli id delle frane devono
restare quelli, o `iffi_landslides` si riempirebbe di doppioni.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, Polygon

from limen.data.db import acquire
from limen.integrations.geoserver_source import vettori
from limen.integrations.geoserver_source.loader import _load_idraulica, _load_iffi

pytestmark = pytest.mark.integration

_IDRAULICA = "Mosaicatura_ISPRA_2020_aree_pericolosita_idraulica"


def _scrivi(
    path: Path, geometrie: list[object], attributi: dict[str, list[object]], epsg: int
) -> None:
    import geopandas as gpd

    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(attributi, geometry=geometrie, crs=f"EPSG:{epsg}").to_file(path)


@pytest.fixture
def cartella(tmp_path: Path) -> Path:
    # Un quadrato di 1 km vicino a Bari in UTM 32N, e lo stesso posto in LAEA.
    bari_utm = Polygon(
        [
            (1_100_000, 4_560_000),
            (1_101_000, 4_560_000),
            (1_101_000, 4_561_000),
            (1_100_000, 4_561_000),
        ]
    )
    bari_laea = Polygon(
        [
            (4_899_000, 2_028_000),
            (4_900_000, 2_028_000),
            (4_900_000, 2_029_000),
            (4_899_000, 2_029_000),
        ]
    )
    _scrivi(
        tmp_path / "frane_poly_puglia_opendata" / "frane_poly_opendataPolygon.shp",
        [bari_utm, bari_utm.buffer(-100)],
        {
            "id_frana": ["0710012300", "0710012301"],
            "nome_tipo": ["Scivolamento", "Colata"],
            "ID_NUM": [3.0, 4.5],
        },
        32632,
    )
    _scrivi(
        tmp_path / "frane_line_puglia_opendata" / "frane_line_opendataLine.shp",
        [LineString([(1_100_000, 4_560_000), (1_100_500, 4_560_500)])],
        {"id_frana": ["0710012302"], "nome_tipo": ["Crollo"]},
        32632,
    )
    for sigla, nome in (("HPH", "elevata"), ("LPH", "bassa")):
        _scrivi(
            tmp_path
            / _IDRAULICA
            / f"{sigla}_Mosaicatura_ISPRA_2020_pericolosita_idraulica_{nome}.shp",
            [bari_laea],
            {"scenario": [sigla]},
            3035,
        )
    _scrivi(
        tmp_path / "Limiti01012023_g" / "Com01012023_g" / "Com01012023_g_WGS84.shp",
        [Point(16.87, 41.12).buffer(0.05)],
        {"PRO_COM_T": ["072006"], "COMUNE": ["Bari"]},
        4326,
    )
    return tmp_path


async def test_tabelle_come_le_faceva_geoserver(pg_pool: object, cartella: Path) -> None:
    esito = await vettori.carica_vettori(cartella, forza=True)
    assert not esito.fallite

    hph = "mosaicatura_ispra_2020_aree_pericolosita_idraulica_hph_4c7713bb"
    assert set(esito.caricate) == {
        "frane_poly_puglia_opendata",
        "frane_line_puglia_opendata",
        hph,
        "mosaicatura_ispra_2020_aree_pericolosita_idraulica_lph_a835c30c",
        "com01012023_g",
    }
    async with acquire() as conn:
        righe = await conn.fetch(
            "SELECT fid, id_frana, nome_tipo, id_num, ST_SRID(geom) AS srid, "
            "GeometryType(geom) AS tipo FROM sorgenti.frane_poly_puglia_opendata ORDER BY fid"
        )
        assert [(r["fid"], r["id_frana"], r["id_num"]) for r in righe] == [
            (1, "0710012300", "3"),
            (2, "0710012301", "4.5"),
        ]
        assert {(r["srid"], r["tipo"]) for r in righe} == {(4326, "MULTIPOLYGON")}

        # Il loader di oggi le legge senza saperne niente.
        frane = await _load_iffi(conn, vettori.SCHEMA, "puglia")
        # L'id è «tabella:id_frana», come quando la tabella stava in GeoServer.
        assert {f.id for f in frane} == {
            "frane_poly_puglia_opendata:0710012300",
            "frane_poly_puglia_opendata:0710012301",
            "frane_line_puglia_opendata:0710012302",
        }
        aree = await _load_idraulica(conn, vettori.SCHEMA, (16.0, 40.0, 18.0, 42.0))
        assert {a.hazard_class for a in aree} == {"P3", "P1"}

        comune = await conn.fetchval(
            "SELECT comune FROM sorgenti.com01012023_g "
            "WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(16.87, 41.12), 4326))"
        )
        assert comune == "Bari"


async def test_un_secondo_giro_senza_cambiamenti_non_scrive(
    pg_pool: object, cartella: Path
) -> None:
    await vettori.carica_vettori(cartella, forza=True)
    esito = await vettori.carica_vettori(cartella)
    assert esito.caricate == {}
    assert len(esito.invariate) == 5
