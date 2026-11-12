"""Misura SWI (#507): controlli, AUC, logistica, lettura del pixel, firma S3."""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta

import numpy as np

from limen.cli.misura_swi import (
    Campione,
    auc,
    auc_appaiata,
    base_meteo,
    controlli,
    fuori_regione,
    logistica,
)
from limen.integrations.copernicus_land.swi import Chiavi, _firma, scegli, valore_del_punto


def test_controlli_lontani_da_ogni_frana_vicina() -> None:
    giorno = date(2019, 11, 20)
    tutti = {(1188, 4428): [giorno, giorno + timedelta(days=10)]}
    scelti = controlli([(11.88, 44.28, giorno)], tutti, rng=random.Random(1))[0]
    assert len(scelti) == 4
    for g in scelti:
        assert 4 <= abs((g - giorno).days) <= 30
        assert abs((g - (giorno + timedelta(days=10))).days) > 3


def test_auc_appaiata_e_mann_whitney() -> None:
    campioni = [
        Campione(0, True, 0, 0, date(2020, 1, 1), "r", {"v": 3.0}),
        Campione(0, False, 0, 0, date(2020, 1, 9), "r", {"v": 1.0}),
        Campione(0, False, 0, 0, date(2020, 1, 19), "r", {"v": 3.0}),
        Campione(1, True, 0, 0, date(2020, 2, 1), "r", {"v": None}),
        Campione(1, False, 0, 0, date(2020, 2, 9), "r", {"v": 9.0}),
    ]
    assert auc_appaiata(campioni, "v") == (0.75, 2)
    etichette = np.array([True, True, False, False])
    assert auc(np.array([0.9, 0.8, 0.1, 0.2]), etichette) == 1.0
    assert auc(np.array([0.5, 0.5, 0.5, 0.5]), etichette) == 0.5


def test_logistica_trova_il_segno() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 1))
    y = (x[:, 0] + rng.normal(scale=0.5, size=400) > 0).astype(float)
    beta = logistica(x, y)
    assert beta[1] > 1.0


def test_fuori_regione_inutile_resta_pari() -> None:
    rng = random.Random(3)
    campioni: list[Campione] = []
    for i in range(240):
        regione = "a" if i < 120 else "b"
        frana = i % 5 == 0
        pioggia = rng.gauss(2.0 if frana else 0.0, 1.0)
        campioni.append(
            Campione(
                i // 5,
                frana,
                0,
                0,
                date(2020, 1, 1),
                regione,
                {"p": pioggia, "rumore": rng.random()},
            )
        )
    per_regione, base, con = fuori_regione([c for c in campioni for _ in range(2)], ["p"], "rumore")
    assert set(per_regione) == {"a", "b"}
    assert base > 0.8
    assert abs(con - base) < 0.03


def test_base_meteo_finestre_e_mezzanotte() -> None:
    giorni = [date(2019, 10, 1) + timedelta(days=k) for k in range(40)]
    dati = {
        "daily": {"time": [g.isoformat() for g in giorni], "precipitation_sum": [1.0] * 40},
        "hourly": {"time": ["2019-11-05T00:00"], "soil_moisture_0_to_7cm": [0.31]},
    }
    x = base_meteo(dati, date(2019, 11, 5))
    assert x["pioggia_3g"] == np.log1p(3.0)
    assert x["pioggia_30g"] == np.log1p(30.0)
    assert x["suolo_om"] == 0.31
    assert base_meteo({}, date(2019, 11, 5)) == {
        "pioggia_3g": None,
        "pioggia_30g": None,
        "suolo_om": None,
    }


def test_valore_del_punto_centro_o_mediana() -> None:
    finestra = np.array([[255, 255, 255], [255, 120, 255], [255, 255, 255]])
    assert valore_del_punto(finestra, 255, 0.5, 0.0) == 60.0
    mascherato = np.array([[100, 255, 255], [255, 255, 255], [255, 255, 120]])
    assert valore_del_punto(mascherato, 255, 0.5, 0.0) == 55.0
    assert valore_del_punto(np.full((3, 3), 255), 255, 0.5, 0.0) is None


def test_scegli_il_file_cog_del_tempo_caratteristico() -> None:
    cartella = "CLMS/x/2019/05/10/c_gls_SWI1km_201905101200_CEURO_SCATSAR_V1.0.2_cog/"
    chiavi = [
        cartella + "c_gls_SWI1km-QFLAG020_201905101200_CEURO_SCATSAR_V1.0.2.tiff",
        cartella + "c_gls_SWI1km-SWI020_201905101200_CEURO_SCATSAR_V1.0.2.tiff",
        cartella + "c_gls_SWI1km-SWI002_201905101200_CEURO_SCATSAR_V1.0.2.tiff",
    ]
    assert scegli(chiavi, "020") == chiavi[1]
    assert scegli(chiavi, "100") is None


def test_firma_sigv4_stabile() -> None:
    intestazioni = _firma(
        Chiavi("AKIDEXAMPLE", "segreto"),
        "list-type=2&prefix=x",
        datetime(2026, 11, 12, 10, 0, tzinfo=UTC),
    )
    assert intestazioni["x-amz-date"] == "20261112T100000Z"
    assert intestazioni["Authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20261112/default/s3/aws4_request, "
    )
    assert len(intestazioni["Authorization"].rsplit("Signature=", 1)[1]) == 64
