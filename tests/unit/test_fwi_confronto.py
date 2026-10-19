"""Il confronto con l'FWI ufficiale Copernicus (#280): numeri, e niente zeri finti."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from limen.cli.fwi_confronto import coppie
from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds
from limen.core.scoring.wildfire.confronto import classe_fwi, confronta
from limen.data.repos.fwi_state_repo import GiornoCatena
from limen.integrations.effis.fwi_wms import campiona, parametri


@pytest.fixture
def soglie() -> WildfireThresholds:
    s = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(s, WildfireThresholds)
    return s


def test_le_classi_sono_le_bande_effis(soglie: WildfireThresholds) -> None:
    def c(fwi: float) -> RiskLevel:
        return classe_fwi(
            fwi, normalisation_max=soglie.fwi.normalisation_max, cutoffs=soglie.classes
        )

    assert c(3) is RiskLevel.None_
    assert c(15) is RiskLevel.Moderate
    assert c(30) is RiskLevel.High
    assert c(60) is RiskLevel.VeryHigh


def test_confronta_dice_di_quanto_e_in_che_direzione(soglie: WildfireThresholds) -> None:
    esiti = confronta(
        {"fwi": [(30.0, 25.0), (10.0, 10.0), (5.0, 8.0)], "dc": []},
        normalisation_max=soglie.fwi.normalisation_max,
        cutoffs=soglie.classes,
    )
    assert [e.componente for e in esiti] == ["fwi"]
    fwi = esiti[0]
    assert fwi.n == 3
    assert fwi.bias == pytest.approx((5 + 0 - 3) / 3)
    assert fwi.mae == pytest.approx(8 / 3)
    assert fwi.r is not None and fwi.r > 0.9
    # 30 e 25 sono entrambi «High», 10 e 10 uguali; 5 è «nessuno», 8 è «basso».
    assert fwi.stessa_classe == pytest.approx(2 / 3)
    assert fwi.sopra == 0.0


def test_le_coppie_saltano_i_giorni_senza_riferimento() -> None:
    nodo = (16.5, 40.5)
    nostri = [
        GiornoCatena(
            lon=16.5,
            lat=40.5,
            day=date(2026, 9, 1),
            chain_days=120,
            componenti={"fwi": 20.0, "dc": 300.0},
        ),
        GiornoCatena(
            lon=16.5,
            lat=40.5,
            day=date(2026, 9, 2),
            chain_days=121,
            componenti={"fwi": 22.0, "dc": 305.0},
        ),
    ]
    rif = {(nodo, date(2026, 9, 1)): {"fwi": 18.0}}
    assert coppie(nostri, rif) == {"fwi": [(20.0, 18.0)]}


def _tiff(valori: np.ndarray) -> bytes:
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=valori.shape[1],
            height=valori.shape[0],
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(6.0, 47.6, 0.05, 0.05),
        ) as r:
            r.write(valori.astype("float32"), 1)
        return bytes(mem.read())


def test_campiona_legge_il_pixel_del_nodo() -> None:
    valori = np.zeros((232, 260))
    # Il pixel di (16.5, 40.5): colonna (16.5-6)/0.05 = 210, riga (47.6-40.5)/0.05 = 142.
    valori[142, 210] = 27.5
    out = campiona(_tiff(valori), [(16.5, 40.5), (7.0, 47.0)])
    assert out == {(16.5, 40.5): 27.5, (7.0, 47.0): 0.0}


def test_un_raster_tutto_a_zero_e_assenza_non_calma() -> None:
    # EFFIS oltre dopodomani risponde 200 con un raster di zeri.
    assert campiona(_tiff(np.zeros((232, 260))), [(16.5, 40.5)]) is None


def test_la_richiesta_wms_e_quella_verificata() -> None:
    p = parametri(date(2026, 10, 19), "fwi")
    assert p["LAYERS"] == "mf010.fwi"
    assert p["BBOX"] == "36.0,6.0,47.6,19.0"
    assert (p["WIDTH"], p["HEIGHT"]) == ("260", "232")
    assert p["FORMAT"] == "image/tiff"


def test_l_assestamento_e_quello_del_motore(soglie: WildfireThresholds) -> None:
    fwi = soglie.fwi
    # Una catena lunga partita in primavera è assestata.
    assert not fwi.in_assestamento(date(2026, 9, 20), 150)
    # Troppo corta.
    assert fwi.in_assestamento(date(2026, 9, 20), fwi.spinup_days - 1)
    # Lunga abbastanza ma partita a metà estate: il DC non ha la siccità di
    # stagione (#201).
    assert fwi.in_assestamento(date(2026, 9, 20), fwi.spinup_days + 5)
