"""Le tile del rilievo dal DTM (#318)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from limen.integrations.dem.terrain_tiles import (
    codifica,
    decodifica,
    genera,
    riquadro_aoi,
    tile_del_riquadro,
)


def test_la_codifica_mapbox_torna_al_decimetro() -> None:
    quote = np.array([[-50.0, 0.0], [1065.3, 4807.8]])
    assert np.allclose(decodifica(codifica(quote)), quote, atol=0.05)
    # Il livello del mare ha la sua terna nota: (1, 134, 160).
    assert codifica(np.array([[0.0]]))[:, 0, 0].tolist() == [1, 134, 160]


def test_le_tile_del_riquadro_coprono_l_area() -> None:
    puglia = riquadro_aoi("it-puglia")
    assert 14.9 < puglia[0] < 15.0 and 41.9 < puglia[3] < 42.3
    # A zoom 5 la Puglia sta in poche tile, e quella di Bari c'è.
    assert (17, 11) in tile_del_riquadro(5, puglia)
    with pytest.raises(ValueError):
        riquadro_aoi("it-atlantide")


def _dtm(percorso: Path) -> None:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin

    # Una collina di 1000 m su 20 km, a 50 m di pixel, col mare a bordo.
    n = 400
    yy, xx = np.mgrid[0:n, 0:n]
    quota = 1000.0 * np.exp(-(((xx - n / 2) ** 2 + (yy - n / 2) ** 2) / (n / 6) ** 2))
    quota[:, :20] = -9999.0
    with rasterio.open(
        percorso,
        "w",
        driver="GTiff",
        width=n,
        height=n,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(16.8, 41.2, 0.0005, 0.0005),
        nodata=-9999.0,
    ) as dst:
        dst.write(quota.astype("float32"), 1)
        dst.build_overviews([2, 4, 8, 16], Resampling.average)


def test_genera_scrive_le_tile_e_non_rifa_una_sorgente_invariata(tmp_path: Path) -> None:
    from pmtiles.reader import MmapSource, Reader
    from rasterio.io import MemoryFile

    dtm = tmp_path / "dtm.tif"
    _dtm(dtm)
    uscita = tmp_path / "rilievo-prova.pmtiles"
    riquadro = (16.8, 41.0, 17.0, 41.2)
    esito = genera(dtm, uscita, riquadro=riquadro, zoom=(8, 10), attribuzione="prova")
    assert not esito.saltato and esito.tile > 0

    with uscita.open("rb") as f:
        r = Reader(MmapSource(f))
        assert r.metadata()["encoding"] == "mapbox"
        assert r.metadata()["attribution"] == "prova"
        z, x, y = 10, *tile_del_riquadro(10, (16.9, 41.1, 16.9, 41.1))[0]
        with MemoryFile(r.get(z, x, y)) as m, m.open() as png:
            cima = decodifica(png.read()).max()
    assert 800 < cima <= 1000

    assert genera(dtm, uscita, riquadro=riquadro, zoom=(8, 10), attribuzione="prova").saltato
    # Un altro zoom è un'altra impronta: si rifà. Anche un'altra attribuzione,
    # che sta nei metadati e deve arrivare sulla mappa.
    assert not genera(dtm, uscita, riquadro=riquadro, zoom=(8, 9), attribuzione="prova").saltato
    assert not genera(dtm, uscita, riquadro=riquadro, zoom=(8, 9), attribuzione="altra").saltato


def test_un_dtm_in_gradi_sceglie_l_overview_in_metri(tmp_path: Path) -> None:
    from limen.integrations.dem.terrain_tiles import _sorgente_per_zoom

    dtm = tmp_path / "dtm.tif"
    _dtm(dtm)
    # Pixel di 0,0005° ≈ 42 m a 41°: a zoom 11 (≈ 57 m) va bene il pieno o
    # l'overview da 2 al massimo, a zoom 5 (≈ 3,7 km) la più grossa (da 16).
    with _sorgente_per_zoom(dtm, 11) as fine, _sorgente_per_zoom(dtm, 5) as grosso:
        assert fine.width >= 200
        assert grosso.width == 25
