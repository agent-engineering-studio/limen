"""EGMS Ortho L3: mosaico e statistiche per cella."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from egms_client import tiles_for_bounds
from egms_client.mosaic import Mosaic
from egms_client.mosaic import mosaic as mosaico

from limen.integrations.egms.aggregate import Cella, per_cella, su_griglia


def test_le_tile_sono_le_centinaia_di_km_dell_angolo() -> None:
    assert tiles_for_bounds(4_750_000, 1_950_000, 4_760_000, 1_960_000) == [(47, 19)]
    assert tiles_for_bounds(4_790_000, 1_990_000, 4_810_000, 2_010_000) == [
        (47, 19),
        (47, 20),
        (48, 19),
        (48, 20),
    ]


def _griglia(verticale: list[list[float]], est: list[list[float]]) -> tuple[Mosaic, Mosaic]:
    return (
        Mosaic(np.array(verticale, dtype="float32"), left=0.0, top=400.0),
        Mosaic(np.array(est, dtype="float32"), left=0.0, top=400.0),
    )


def test_la_cella_prende_i_pixel_col_centro_dentro() -> None:
    nan = float("nan")
    # 4 x 4 pixel da 100 m; la cella (100..300, 100..300) contiene i centri
    # delle colonne 1-2 e delle righe 1-2.
    v = [[9, 9, 9, 9], [9, 1, 2, 9], [9, 3, nan, 9], [9, 9, 9, 9]]
    e = [[9, 9, 9, 9], [9, 0, 0, 9], [9, 4, 1, 9], [9, 9, 9, 9]]
    (r,) = per_cella([Cella("c", 100.0, 100.0, 300.0, 300.0)], *_griglia(v, e))
    assert r.scatterer_count == 3
    assert r.velocita_verticale_mmy == pytest.approx(2.0)
    assert r.velocita_est_mmy == pytest.approx(0.0)
    # moduli 1, 2, 5: il 90° percentile sta verso il pixel che si muove.
    assert r.insar_velocity_mmy == pytest.approx(np.percentile([1.0, 2.0, 5.0], 90))
    # La coda che scende di più, e tre pixel validi su quattro.
    assert r.velocita_verticale_p10_mmy == pytest.approx(np.percentile([1.0, 2.0, 3.0], 10))
    assert r.copertura == pytest.approx(0.75)


def test_una_cella_senza_pixel_validi_non_e_ferma() -> None:
    nan = float("nan")
    v = [[nan, nan], [nan, nan]]
    (r,) = per_cella([Cella("c", 0.0, 200.0, 200.0, 400.0)], *_griglia(v, v))
    assert r.scatterer_count == 0
    assert r.insar_velocity_mmy is None
    assert r.velocita_verticale_mmy is None
    assert r.accelerazione_verticale_mmy2 is None
    assert r.copertura == 0.0


def test_una_cella_fuori_dalla_griglia_non_alza() -> None:
    v = [[1.0]]
    (r,) = per_cella([Cella("c", 5000.0, 5000.0, 6000.0, 6000.0)], *_griglia(v, v))
    assert r.scatterer_count == 0
    assert r.copertura is None


def _tiff(path: Path, left: float, top: float, dati: list[list[float]]) -> None:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    arr = np.array(dati, dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:3035",
        transform=from_origin(left, top, 100.0, 100.0),
        nodata=-9999.0,
    ) as dst:
        dst.write(arr, 1)


def test_il_mosaico_cuce_due_tile_e_lascia_nan_dove_mancano(tmp_path: Path) -> None:
    a, b = tmp_path / "a.tiff", tmp_path / "b.tiff"
    _tiff(a, 0.0, 200.0, [[1, 2], [3, -9999]])
    _tiff(b, 200.0, 200.0, [[5, 6], [7, 8]])
    m = mosaico([a, b], minx=0.0, miny=0.0, maxx=500.0, maxy=200.0).values
    assert m.shape == (2, 5)
    assert m[0, :4].tolist() == [1, 2, 5, 6]
    assert np.isnan(m[1, 1])
    assert np.isnan(m[:, 4]).all()


def test_una_tile_con_l_etichetta_ignf_entra_nel_mosaico(tmp_path: Path) -> None:
    """E42N26 dichiara IGNF:ETRS89LAEA: stessi parametri di EPSG:3035."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.crs import CRS
    from rasterio.transform import from_origin

    path = tmp_path / "ignf.tiff"
    wkt = CRS.from_epsg(3035).to_wkt().replace("ETRS89-extended / LAEA Europe", "ETRS89 LAEA")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=1,
        width=2,
        count=1,
        dtype="float32",
        crs=CRS.from_wkt(wkt),
        transform=from_origin(100.0, 100.0, 100.0, 100.0),
        nodata=-9999.0,
    ) as dst:
        dst.write(np.array([[4.0, 5.0]], dtype="float32"), 1)
    m = mosaico([path], minx=0.0, miny=0.0, maxx=300.0, maxy=100.0).values
    assert np.isnan(m[0, 0])
    assert m[0, 1:].tolist() == [4.0, 5.0]


def test_una_tile_in_un_altra_proiezione_alza(tmp_path: Path) -> None:
    _tiff_crs = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    path = tmp_path / "utm.tiff"
    with _tiff_crs.open(
        path,
        "w",
        driver="GTiff",
        height=1,
        width=1,
        count=1,
        dtype="float32",
        crs="EPSG:32633",
        transform=from_origin(0.0, 100.0, 100.0, 100.0),
    ) as dst:
        dst.write(np.array([[1.0]], dtype="float32"), 1)
    with pytest.raises(ValueError, match="LAEA"):
        mosaico([path], minx=0.0, miny=0.0, maxx=100.0, maxy=100.0)


def test_accelerazione_con_segno_sugli_stessi_pixel_della_velocita(tmp_path: Path) -> None:
    nan = float("nan")
    # I centri dei pixel: (150, 250) è la riga 1, colonna 1 di una griglia con
    # l'angolo in (0, 400); un punto fuori dalla griglia si ignora.
    u = tmp_path / "u.attributes.csv"
    u.write_text(
        "pid,easting,northing,acceleration,seasonality\n"
        "a,150,250,-3.0,2.0\nb,250,250,1.0,4.0\nc,150,150,,6.0\n"
        "d,250,150,50.0,90.0\ne,9050,50,7.0,7.0\n"
    )
    uno = [[1.0] * 4 for _ in range(4)]
    verticale, est = _griglia(uno, uno)
    # Il pixel (riga 2, colonna 2) non ha la velocità: la sua accelerazione
    # (50) e la sua stagionalità (90) non entrano, come non entra lui.
    verticale.values[2, 2] = nan
    acc = su_griglia([u], "acceleration", verticale)
    assert acc[1, 1] == -3.0 and acc[1, 2] == 1.0 and np.isnan(acc[2, 1])
    (r,) = per_cella(
        [Cella("c", 100.0, 100.0, 300.0, 300.0)],
        verticale,
        est,
        accelerazione=acc,
        stagionalita=su_griglia([u], "seasonality", verticale),
    )
    assert r.scatterer_count == 3
    # Con segno: un versante che accelera verso il basso resta negativo.
    assert r.accelerazione_verticale_mmy2 == pytest.approx(-1.0)
    assert r.accelerazione_verticale_p10_mmy2 == pytest.approx(np.percentile([-3.0, 1.0], 10))
    assert r.insar_accel_mmy2 is None
    assert r.stagionalita_verticale_mm == pytest.approx(4.0)


def test_senza_csv_accelerazione_e_stagionalita_restano_nulle() -> None:
    v = [[1.0, 1.0], [1.0, 1.0]]
    (r,) = per_cella([Cella("c", 0.0, 200.0, 200.0, 400.0)], *_griglia(v, v))
    assert r.scatterer_count == 4
    assert r.accelerazione_verticale_mmy2 is None and r.stagionalita_verticale_mm is None


def _su_griglia_di_prima(attributi: list[Path], colonna: str, come: Any) -> Any:
    """``su_griglia`` com'era fino a egms-client 0.11 (gli ``.npz`` di Limen): per la parità."""
    righe, colonne = come.values.shape
    out = np.full((righe, colonne), np.nan, dtype="float32")
    for path in attributi:
        with np.load(path) as a:
            col = np.floor((a["easting"] - come.left) / come.pixel).astype(np.int64)
            riga = np.floor((come.top - a["northing"]) / come.pixel).astype(np.int64)
            dentro = (riga >= 0) & (riga < righe) & (col >= 0) & (col < colonne)
            out[riga[dentro], col[dentro]] = a[colonna][dentro]
    return out


def test_gli_attributi_migrati_danno_le_stesse_celle(tmp_path: Path) -> None:
    """Gli ``.npz`` di prima, migrati in ``.attributes.csv``: stesse griglie, stesse celle."""
    from limen.integrations.egms.clms import migra_attributi

    rng = np.random.default_rng(380)
    verticale, est = _griglia(
        rng.normal(-2, 3, (20, 20)).tolist(), rng.normal(0, 1, (20, 20)).tolist()
    )
    # Due tile: punti sparsi, uno fuori dalla griglia, valori con molte cifre e NaN.
    npz = []
    for i, n in enumerate((150, 90)):
        path = tmp_path / f"EGMS_L3_E4{i}N20_100km_U_2020_2025_1.attributi.npz"
        acc = rng.normal(0, 1, n)
        acc[::7] = np.nan
        np.savez(
            path,
            easting=np.floor(rng.uniform(0, 2100, n) / 100) * 100 + 50,
            northing=np.floor(rng.uniform(-100, 2000, n) / 100) * 100 + 50,
            acceleration=acc,
            seasonality=rng.uniform(0, 9, n),
        )
        npz.append(path)
    # Un CSV senza le colonne lasciava un .npz vuoto.
    vuoto = tmp_path / "EGMS_L3_E42N20_100km_U_2020_2025_1.attributi.npz"
    np.savez(
        vuoto, **{c: np.empty(0) for c in ("easting", "northing", "acceleration", "seasonality")}
    )
    npz.append(vuoto)
    prima = {c: _su_griglia_di_prima(npz, c, verticale) for c in ("acceleration", "seasonality")}

    assert migra_attributi(tmp_path) == 3
    assert not list(tmp_path.glob("*.npz"))
    csv = sorted(tmp_path.glob("*.attributes.csv"))
    assert len(csv) == 3
    for c in ("acceleration", "seasonality"):
        np.testing.assert_array_equal(su_griglia(csv, c, verticale), prima[c])
    celle = [Cella(f"c{i}", x, 0.0, x + 1000.0, 1000.0) for i, x in enumerate((0.0, 1000.0))]
    di_prima = per_cella(
        celle,
        verticale,
        est,
        accelerazione=prima["acceleration"],
        stagionalita=prima["seasonality"],
    )
    ora = per_cella(
        celle,
        verticale,
        est,
        accelerazione=su_griglia(csv, "acceleration", verticale),
        stagionalita=su_griglia(csv, "seasonality", verticale),
    )
    assert ora == di_prima
    # Una seconda volta non c'è niente da migrare.
    assert migra_attributi(tmp_path) == 0


def test_un_file_senza_colonne_non_entra(tmp_path: Path) -> None:
    v = [[1.0, 1.0], [1.0, 1.0]]
    verticale, _ = _griglia(v, v)
    vecchio = tmp_path / "x.attributes.csv"
    vecchio.write_text("pid,easting,northing,mean_velocity\na,50,350,3\n")
    assert np.isnan(su_griglia([vecchio], "acceleration", verticale)).all()
