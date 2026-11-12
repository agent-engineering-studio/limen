"""Lettura dei catasti regionali degli incendi e scelta della verità del backtest (#498)."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from shapely import to_wkb
from shapely.geometry import Point

from limen.cli.backtest_wildfire import Verita, leggi_verita
from limen.cli.catasti_incendi import leggi, leggi_data


@pytest.mark.parametrize(
    ("valore", "atteso"),
    [
        ("2011-08-28", date(2011, 8, 28)),
        ("08/04/2024", date(2024, 4, 8)),
        ("2021/05/13", date(2021, 5, 13)),
        ("2006-04-08Z", date(2006, 4, 8)),
        (np.datetime64("2010-10-16"), date(2010, 10, 16)),
        ("NaT", None),
        ("", None),
        (None, None),
        ("ieri", None),
    ],
)
def test_leggi_data_nei_formati_degli_enti(valore: object, atteso: date | None) -> None:
    assert leggi_data(valore) == atteso


def _zip(tmp_path: Path, campi: dict[str, list[str]], crs: str = "EPSG:25832") -> Path:
    import pyogrio

    n = len(next(iter(campi.values())))
    shp = tmp_path / "incendi.shp"
    pyogrio.raw.write(
        str(shp),
        np.array([to_wkb(Point(600_000 + i * 50, 4_900_000).buffer(10)) for i in range(n)]),
        [np.array(v, dtype=object) for v in campi.values()],
        fields=list(campi),
        geometry_type="Polygon",
        crs=crs,
        driver="ESRI Shapefile",
    )
    path = tmp_path / "catasto.zip"
    with zipfile.ZipFile(path, "w") as archivio:
        for f in tmp_path.glob("incendi.*"):
            archivio.write(f, f"dati/{f.name}")
    return path


def test_leggi_tiene_la_chiave_dell_ente_e_scarta_le_righe_senza_data(tmp_path: Path) -> None:
    path = _zip(
        tmp_path,
        {"INC_ID": ["7", "7", "9"], "DATA_INC": ["28/08/2011", "28/08/2011", ""]},
    )

    poligoni, senza_data = leggi(path)

    assert senza_data == 1
    assert [(p.chiave, p.giorno, p.srid) for p in poligoni] == [
        ("7", date(2011, 8, 28), 25832),
        ("7", date(2011, 8, 28), 25832),
    ]


def test_senza_chiave_ogni_poligono_e_un_incendio(tmp_path: Path) -> None:
    path = _zip(tmp_path, {"numIncen": ["0", "0"], "data": ["2010-10-16", "2010-10-17"]})

    poligoni, _ = leggi(path)

    assert len({p.chiave for p in poligoni}) == 2


def test_leggi_senza_campo_data_e_un_errore(tmp_path: Path) -> None:
    path = _zip(tmp_path, {"COMUNE": ["PULA"]})

    with pytest.raises(ValueError, match="nessun campo data"):
        leggi(path)


def test_verita_di_default_e_effis_senza_filtro() -> None:
    v = leggi_verita("effis", "")

    assert v == Verita()
    assert v.suffisso == ""
    assert v.descrizione == "perimetri EFFIS"


def test_verita_catasti_per_classe_di_superficie() -> None:
    v = leggi_verita("catasti", "1-10")

    assert (v.ettari_min, v.ettari_max) == (1.0, 10.0)
    assert v.suffisso == "_catasti_1-10ha"
    assert v.descrizione == "catasti regionali degli incendi, incendi da 1 a 10 ha"


def test_verita_con_un_estremo_solo() -> None:
    assert leggi_verita("tutte", "100-") == Verita(fonte="tutte", ettari_min=100.0)
    assert leggi_verita("effis", "-1").suffisso == "_-1ha"


@pytest.mark.parametrize(("fonte", "ettari"), [("firms", ""), ("effis", "10"), ("effis", "a-b")])
def test_verita_illeggibile_e_un_errore(fonte: str, ettari: str) -> None:
    with pytest.raises(ValueError):
        leggi_verita(fonte, ettari)


async def test_una_pagina_html_al_posto_dello_zip_e_un_anno_assente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from limen.cli import catasti_incendi

    risposte = {"a.zip": b"PK\x03\x04resto", "b.zip": b"<html>non trovato</html>"}

    async def finto(_metodo: str, url: str, **_kw: object) -> httpx.Response:
        return httpx.Response(200, content=risposte[url])

    monkeypatch.setattr(catasti_incendi, "fetch_with_retry", finto)
    monkeypatch.setattr(catasti_incendi, "cartella", lambda: tmp_path)
    ente = catasti_incendi.Ente(
        fonte="prova",
        licenza="CC BY 4.0",
        attribuzione="prova",
        file=lambda _a: [catasti_incendi.File(n, n, definitivo=False) for n in ("a.zip", "b.zip")],
        tollera_assenti=True,
    )

    percorsi = await catasti_incendi.scarica(ente, date(2026, 11, 12))

    assert [p.name for p in percorsi] == ["a.zip"]
    assert not (tmp_path / "b.zip").exists()


def test_l_impronta_ignora_l_ora_della_risposta_wfs() -> None:
    from limen.cli.catasti_incendi import impronta

    a = b'{"features":[],"timeStamp":"2026-11-12T15:13:42.182Z","crs":{}}'
    b = b'{"features":[],"timeStamp":"2026-11-13T09:00:00.000Z","crs":{}}'

    assert impronta(a) == impronta(b)
    assert impronta(a) != impronta(a.replace(b"[]", b"[1]"))
