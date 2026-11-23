"""Le parti di ``carica-vettori`` che non chiedono un database (#670).

La mosaicatura PAI v. 5.0 è un File Geodatabase: qui si controlla che entri
con le convenzioni degli shapefile (nome della tabella dalla cartella, colonne
in minuscolo, righe numerate da 1 nell'ordine del file) e che dei due mosaici
PAI si carichi quello scelto. Il caricamento vero è in
``tests/integration/test_carica_vettori.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from ispra_idrogeo import MOSAICS
from shapely import from_wkb
from shapely.geometry import MultiPolygon, Polygon

from limen.integrations.geoserver_source import vettori

_V4 = MOSAICS["pai_frane"]
_V5 = MOSAICS["pai_frane_2024"]
_CLASSI = ["Media P2", "Elevata P3", "Aree di Attenzione AA"]


def _quadrato(x: float) -> MultiPolygon:
    return MultiPolygon([Polygon([(x, 0), (x + 100, 0), (x + 100, 100), (x, 100)])])


def _gdb(cartella: Path) -> Path:
    """Un geodatabase come quello di ISPRA: ``<mosaico>/<mosaico>.gdb``, UTM 32N."""
    import geopandas as gpd

    gdb = cartella / _V5 / f"{_V5}.gdb"
    gdb.parent.mkdir(parents=True)
    gpd.GeoDataFrame(
        {"Shape_Area": [10000.0, 10000.0, 10000.0], "per_fr_ita": _CLASSI},
        geometry=[_quadrato(500_000 + 1000 * i) for i in range(3)],
        crs="EPSG:32632",
    ).to_file(gdb, driver="OpenFileGDB", layer="Mosaicatura_ISPRA_2024_aree_pericolosita_frana_PAI")
    return gdb


def _cartella(tmp_path: Path) -> tuple[Path, Path]:
    gdb = _gdb(tmp_path)
    for cartella in (_V4, "Mosaicatura_ISPRA_2020_aree_pericolosita_idraulica", "altro"):
        (tmp_path / cartella).mkdir()
        (tmp_path / cartella / "dati.shp").touch()
    return tmp_path / _V4 / "dati.shp", gdb


def test_il_nome_della_tabella_del_gdb_viene_dalla_cartella(tmp_path: Path) -> None:
    v4, gdb = _cartella(tmp_path)
    assert vettori.nome_tabella(gdb) == "mosaicatura_ispra_2024_pericolosita_frana_pai"
    assert vettori.nome_tabella(v4) == "mosaicatura_ispra_2020_2021_aree_pericolosita_frana_pai"
    # Il PDF della licenza che ISPRA mette accanto al .gdb non cambia il nome.
    (gdb.parent / "Licenza_Condizioni_Uso.pdf").touch()
    assert vettori.nome_tabella(gdb) == "mosaicatura_ispra_2024_pericolosita_frana_pai"


def test_dei_due_mosaici_pai_si_carica_quello_scelto(tmp_path: Path) -> None:
    v4, gdb = _cartella(tmp_path)
    idraulica = tmp_path / "Mosaicatura_ISPRA_2020_aree_pericolosita_idraulica" / "dati.shp"
    assert vettori.sorgenti(tmp_path, "pai_frane") == sorted([v4, idraulica])
    assert vettori.sorgenti(tmp_path, "pai_frane_2024") == sorted([gdb, idraulica])


def test_il_gdb_si_legge_a_blocchi_con_le_convenzioni_degli_shapefile(tmp_path: Path) -> None:
    gdb = _gdb(tmp_path)
    info = vettori._leggi_info(gdb)
    assert info.srid == 32632
    assert info.forme == 3
    colonne = [vettori._identificatore(c, accorcia=False) for c in info.colonne]
    assert "per_fr_ita" in colonne
    assert "geom" not in colonne and "shape" not in colonne

    righe = [r for primo, quanti in ((0, 2), (2, 1)) for r in vettori._blocco(gdb, primo, quanti)]
    assert [r[0] for r in righe] == [1, 2, 3]
    assert [r[2 + colonne.index("per_fr_ita")] for r in righe] == _CLASSI
    assert [from_wkb(r[1]).bounds[0] for r in righe] == [500_000, 501_000, 502_000]


def test_l_impronta_del_gdb_cambia_con_i_suoi_file(tmp_path: Path) -> None:
    gdb = _gdb(tmp_path)
    prima = vettori._impronta(gdb)
    assert prima == vettori._impronta(gdb)
    tabella = max(gdb.glob("*.gdbtable"), key=lambda p: p.stat().st_size)
    os.utime(tabella, ns=(tabella.stat().st_atime_ns, tabella.stat().st_mtime_ns + 1_000_000_000))
    assert vettori._impronta(gdb) != prima
