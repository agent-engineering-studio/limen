"""Il backtest cosismico: lo scuotimento ShakeMap contro le frane sismoindotte."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from shapely.geometry import Point, box

from limen.cli import backtest_cosismico as bc
from limen.integrations.ingv import shakemap_client
from limen.integrations.ingv.shakemap_grid import leggi_griglia

# Una griglia 0,01° sull'Appennino umbro-marchigiano, tutta su terra: PGA che
# cala da ovest a est (colonna 0: 40 %g ... colonna 9: 4 %g), PGV = PGA / 2.
LON0, LAT0, PASSO, NLON, NLAT = 13.00, 42.90, 0.01, 10, 6


def griglia_xml(*, con_evento: bool = True) -> bytes:
    righe = []
    for r in range(NLAT):
        for c in range(NLON):
            pga = 40.0 - 4.0 * c
            righe.append(
                f"{LON0 + c * PASSO:.2f} {LAT0 - r * PASSO:.2f} {9 - c * 0.5} {pga} {pga / 2}"
            )
    evento = (
        f'<event event_id="1" magnitude="6.5" lat="{LAT0 - 0.025}" lon="{LON0}"/>'
        if con_evento
        else ""
    )
    return f"""<?xml version="1.0"?>
<shakemap_grid xmlns="http://earthquake.usgs.gov/eqcenter/shakemap" event_id="1">
{evento}
<grid_specification lon_min="{LON0}" lat_min="{LAT0 - (NLAT - 1) * PASSO:.2f}"
 lon_max="{LON0 + (NLON - 1) * PASSO:.2f}" lat_max="{LAT0}" nlon="{NLON}" nlat="{NLAT}"/>
<grid_field index="1" name="LON" units="dd"/>
<grid_field index="2" name="LAT" units="dd"/>
<grid_field index="3" name="MMI" units="intensity"/>
<grid_field index="4" name="PGA" units="%g"/>
<grid_field index="5" name="PGV" units="cm/s"/>
<grid_data>
{chr(10).join(righe)}
</grid_data>
</shakemap_grid>""".encode()


def test_auc_come_il_conto_a_mano() -> None:
    rng = np.random.default_rng(0)
    casi = rng.integers(0, 6, 40).astype(float)
    controlli = rng.integers(0, 5, 70).astype(float)
    attesa = np.mean([(1.0 if a > b else 0.5 if a == b else 0.0) for a in casi for b in controlli])
    assert bc.auc(casi, controlli) == pytest.approx(attesa)


def test_auc_casi_limite() -> None:
    assert bc.auc([3, 4], [1, 2]) == 1.0
    assert bc.auc([1, 2], [3, 4]) == 0.0
    assert bc.auc([1, 1], [1, 1]) == 0.5
    assert bc.auc([], [1.0]) is None
    assert bc.auc([np.nan], [1.0]) is None


def test_le_frane_dove_trema_di_piu() -> None:
    g = leggi_griglia(griglia_xml())
    terra = box(12.0, 42.0, 14.0, 43.5)
    frane = [
        (13.00, 42.90),  # colonna 0: 40 %g
        (13.001, 42.899),  # stesso punto di griglia: un caso solo
        (13.01, 42.88),  # colonna 1: 36 %g
        (14.50, 42.85),  # fuori mappa
    ]
    esito = bc.valuta(g, frane, terra, event_id="1", soglie_pga_g=(0.02, 0.3))
    assert (esito.frane, esito.frane_in_mappa, esito.casi) == (4, 3, 2)
    assert esito.punti_terra == NLON * NLAT
    # 58 controlli. Il caso a 40 %g ne batte 53 e pareggia con 5; quello a
    # 36 %g ne batte 48, pareggia con 5 e perde con i 5 rimasti a 40 %g.
    assert esito.auc["PGA"] == pytest.approx((53 + 2.5 + 48 + 2.5) / (2 * 58))
    assert esito.auc["PGV"] == esito.auc["PGA"]
    assert esito.auc["vicinanza"] is not None and esito.auc["vicinanza"] > 0.8
    assert esito.pga_mediana_casi_g == pytest.approx(0.38)
    # Tutta la mappa supera 0,02 g: il campo vicino è la mappa intera.
    assert esito.auc_campo_vicino == esito.auc
    debole, forte = esito.soglie
    assert (debole.pga_g, debole.recall, debole.carico) == (0.02, 1.0, 1.0)
    assert debole.lift == pytest.approx(1.0)
    # PGA ≥ 0,3 g: colonne 0-2 (40, 36, 32 %g), 3 su 10 del territorio.
    assert (forte.recall, forte.carico) == (1.0, pytest.approx(0.3))
    assert forte.lift == pytest.approx(1 / 0.3)


def test_il_mare_non_conta() -> None:
    g = leggi_griglia(griglia_xml())
    # Solo le prime cinque colonne sono «terra»: una frana a est è in mare.
    terra = box(12.0, 42.0, LON0 + 4.5 * PASSO, 43.5)
    esito = bc.valuta(g, [(13.00, 42.90), (13.08, 42.88)], terra, event_id="1")
    assert esito.punti_terra == 5 * NLAT
    assert (esito.frane_in_mappa, esito.casi) == (1, 1)


def test_il_campo_vicino_toglie_il_vantaggio_della_lontananza() -> None:
    g = leggi_griglia(griglia_xml())
    terra = box(12.0, 42.0, 14.0, 43.5)
    # Soglia a 0,3 g: restano le colonne 0-2 (40, 36, 32 %g). Una frana a
    # 32 %g è nel campo vicino, ma lì è quella che ha tremato meno.
    esito = bc.valuta(g, [(13.02, 42.90)], terra, event_id="1", pga_min_g=0.3)
    assert esito.auc["PGA"] == pytest.approx((42 + 2.5) / 59)
    assert esito.auc_campo_vicino["PGA"] == pytest.approx(2.5 / 17)


def test_senza_frane_e_senza_epicentro() -> None:
    g = leggi_griglia(griglia_xml(con_evento=False))
    esito = bc.valuta(g, [], box(12.0, 42.0, 14.0, 43.5), event_id="1")
    assert esito.casi == 0 and esito.pga_mediana_casi_g is None
    assert all(v is None for v in esito.auc.values())
    assert all(v is None for v in esito.auc_campo_vicino.values())
    assert all(s.recall == 0.0 for s in esito.soglie)
    nessuna_terra = bc.valuta(g, [(13.0, 42.9)], Point(0, 0).buffer(0.1), event_id="1")
    assert nessuna_terra.punti_terra == 0
    assert all(s.carico == 0.0 and s.lift is None for s in nessuna_terra.soglie)


def test_l_italia_del_seme_e_terra() -> None:
    italia = bc.italia()
    assert italia.contains(Point(13.09, 42.79))  # Norcia
    assert not italia.contains(Point(14.5, 43.0))  # Adriatico


def test_inventario_di_punti_e_poligoni_in_un_altro_crs(tmp_path: Path) -> None:
    fc: dict[str, Any] = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3035"}},
        "features": [
            # Norcia in LAEA Europa, come punto e come quadrato di 100 m attorno.
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": [4609000.0, 2124000.0]},
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [4609000.0, 2124000.0],
                            [4609100.0, 2124000.0],
                            [4609100.0, 2124100.0],
                            [4609000.0, 2124100.0],
                            [4609000.0, 2124000.0],
                        ]
                    ],
                },
            },
            {"type": "Feature", "properties": {}, "geometry": None},
        ],
    }
    file = tmp_path / "frane.geojson"
    file.write_text(json.dumps(fc))
    frane = bc.leggi_inventario(file)
    assert len(frane) == 2
    for lon, lat in frane:
        assert 12.0 < lon < 14.5 and 42.0 < lat < 43.5


def test_parse_eventi() -> None:
    assert bc.parse_eventi(" 7073641=/a/b.shp, 8863681 = c.geojson ,") == [
        ("7073641", Path("/a/b.shp")),
        ("8863681", Path("c.geojson")),
    ]
    assert bc.parse_eventi("") == []
    for storto in ("7073641", "=x.shp", "1="):
        with pytest.raises(ValueError):
            bc.parse_eventi(storto)


def test_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bc, "REPORTS_DIR", tmp_path)
    g = leggi_griglia(griglia_xml())
    terra = box(12.0, 42.0, 14.0, 43.5)
    uno = bc.valuta(g, [(13.0, 42.9)], terra, event_id="1", soglie_pga_g=(0.02,))
    due = bc.valuta(g, [], terra, event_id="2", soglie_pga_g=(0.02,))
    testo = bc.write_report([uno, due], pga_min_g=0.02).read_text()
    assert "| 1 | — | 1 | 1 | 1 | 60 | 0.400 g |" in testo
    assert "0.02 g ← E" in testo
    assert testo.count("media pesata sui casi") == 2
    assert "Nel campo vicino: solo dove E è acceso (PGA ≥ 0.02 g)" in testo
    assert bc.auc_media([uno, due], "PGA") == uno.auc["PGA"]
    assert bc.auc_media([uno, due], "PGA", campo_vicino=True) == uno.auc_campo_vicino["PGA"]
    assert bc.auc_media([due], "PGA") is None


class _Ingv:
    scaricati: list[str] = []  # noqa: RUF012

    def __init__(self, **_: Any) -> None:
        pass

    async def fetch_shakemap_grid(self, event_id: str, *, solleva: bool = False) -> bytes | None:
        assert solleva
        _Ingv.scaricati.append(event_id)
        return griglia_xml() if event_id == "1" else None

    async def fetch_info(self, event_id: str, *, solleva: bool = False) -> Any:
        from ingv_shakemap import parse_info

        return parse_info(
            {
                "output": {},
                "processing": {"shakemap_versions": {"map_version": 3, "map_status": "RELEASED"}},
            }
        )


async def test_run_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inventario = tmp_path / "frane.geojson"
    inventario.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {"type": "Point", "coordinates": [13.0, 42.9]},
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(bc, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(bc, "IngvHttpClient", _Ingv)
    monkeypatch.setenv("LIMEN_BACKTEST_COSISMICO", f"1={inventario},2={inventario}")
    monkeypatch.setenv("LIMEN_BACKTEST_COSISMICO_CACHE", str(tmp_path / "cache"))
    _Ingv.scaricati = []
    assert await bc.run() == 0
    assert await bc.run() == 0
    # La ShakeMap si scarica una volta; l'evento senza mappa si richiede ogni volta.
    assert _Ingv.scaricati == ["1", "2", "2"]
    [report] = tmp_path.glob("backtest_cosismico_*.md")
    assert "| 1 | v3 RELEASED | 1 | 1 | 1 |" in report.read_text()


async def test_run_senza_eventi_o_con_env_storto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIMEN_BACKTEST_COSISMICO", raising=False)
    assert await bc.run() == 1
    monkeypatch.setenv("LIMEN_BACKTEST_COSISMICO", "senza-uguale")
    assert await bc.run() == 1


async def test_run_ingv_irraggiungibile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Giu(_Ingv):
        async def fetch_shakemap_grid(
            self, event_id: str, *, solleva: bool = False
        ) -> bytes | None:
            raise shakemap_client.IngvNonDisponibileError("ShakeMap 1: HTTP 503")

    inventario = tmp_path / "vuoto.geojson"
    inventario.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    monkeypatch.setattr(bc, "IngvHttpClient", _Giu)
    monkeypatch.setenv("LIMEN_BACKTEST_COSISMICO", f"1={inventario}")
    monkeypatch.setenv("LIMEN_BACKTEST_COSISMICO_CACHE", str(tmp_path / "cache"))
    assert await bc.run() == 1
