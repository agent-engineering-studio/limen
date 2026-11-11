"""Confini ISTAT, CORINE e geolitologia per il PostGIS di GeoServer."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import httpx
import pytest
from ispra_idrogeo import IdroGEO

from limen.integrations._http import SharedHttpClient
from limen.integrations.geoserver_source import dati_base

# Due poligoni come li manda il WFS 1.1 del Geoportale: lat/lon.
_GML = b"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs" xmlns:gml="http://www.opengis.net/gml"
  xmlns:ms="http://mapserver.gis.umn.edu/mapserver">
<gml:featureMember><ms:GE.CARTAGEOLITOLOGICA gml:id="a.1">
  <ms:msGeometry><gml:Polygon srsName="EPSG:4326"><gml:exterior><gml:LinearRing>
  <gml:posList srsDimension="2">40 15 40 16 41 16 41 15 40 15</gml:posList>
  </gml:LinearRing></gml:exterior></gml:Polygon></ms:msGeometry>
  <ms:legenda_li>argille</ms:legenda_li>
</ms:GE.CARTAGEOLITOLOGICA></gml:featureMember>
<gml:featureMember><ms:GE.CARTAGEOLITOLOGICA gml:id="a.2">
  <ms:msGeometry><gml:Polygon srsName="EPSG:4326"><gml:exterior><gml:LinearRing>
  <gml:posList srsDimension="2">44 9 44 10 45 10 45 9 44 9</gml:posList>
  </gml:LinearRing></gml:exterior></gml:Polygon></ms:msGeometry>
  <ms:legenda_li>calcari</ms:legenda_li>
</ms:GE.CARTAGEOLITOLOGICA></gml:featureMember>
</wfs:FeatureCollection>"""


def _zip_istat() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("Limiti01012023_g/", b"")
        z.writestr("Limiti01012023_g/Com01012023_g/Com01012023_g_WGS84.shp", b"SHP")
    return buffer.getvalue()


_DTM = bytes(range(256)) * 40  # 10 KB al posto di 22 GB


class _Fonti:
    def __init__(self) -> None:
        self.richieste: list[httpx.Request] = []
        self.gml = _GML
        self.dtm = _DTM
        self.md5 = hashlib.md5(_DTM).hexdigest()
        self.taglia_dopo: int | None = None  # interrompe il DTM a quel byte

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.richieste.append(request)
        if request.url.host == "www.istat.it":
            return httpx.Response(200, content=_zip_istat())
        if "sinanet" in request.url.host:
            return httpx.Response(200, content=request.url.path.rsplit(".", 1)[1].encode())
        if request.url.host == "zenodo.org" and request.url.path.endswith("/24009736"):
            base = "https://zenodo.org/api/records/24009736/files"
            # La maschera delle fonti viene prima del raster, come nel record vero.
            maschera = {
                "key": "HRDTM5m_Mask_20mres.gpkg",
                "size": 3,
                "checksum": "md5:0",
                "links": {"self": f"{base}/HRDTM5m_Mask_20mres.gpkg/content"},
            }
            file = {
                "key": "HRDM5m_20261030_cog.tif",
                "size": len(self.dtm),
                "checksum": f"md5:{self.md5}",
                "links": {"self": f"{base}/HRDM5m_20261030_cog.tif/content"},
            }
            return httpx.Response(200, json={"files": [maschera, file]})
        if request.url.host == "zenodo.org":
            inizio = 0
            if "range" in request.headers:
                inizio = int(request.headers["range"].removeprefix("bytes=").rstrip("-"))
            corpo = self.dtm[inizio:]
            if self.taglia_dopo is not None:
                corpo, self.taglia_dopo = corpo[: self.taglia_dopo], None
            return httpx.Response(206 if inizio else 200, content=corpo)
        if request.url.host == "wms.pcn.minambiente.it":
            assert request.url.params["typeName"] == "GE.CARTAGEOLITOLOGICA"
            return httpx.Response(200, content=self.gml)
        raise AssertionError(str(request.url))


@pytest.fixture
def fonti(monkeypatch: pytest.MonkeyPatch) -> tuple[_Fonti, IdroGEO]:
    finte = _Fonti()
    # Il DTM finto pesa pochi KB: i 5 GB di margine misurerebbero il disco del
    # runner, non il codice (su GitHub /tmp ne ha a volte 1,4).
    monkeypatch.setattr(dati_base, "_DTM_MARGINE_BYTE", 0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(finte))

    async def _get(_cls: type[SharedHttpClient]) -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(SharedHttpClient, "get", classmethod(_get))
    return finte, IdroGEO(client, retries=0)


async def test_tutto_al_primo_giro_niente_al_secondo(
    fonti: tuple[_Fonti, IdroGEO], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    finte, idrogeo = fonti
    monkeypatch.delenv("LIMEN_DEM_RASTER", raising=False)
    # Il raster per cella sta nella cartella di CORINE: non va toccato.
    (tmp_path / "clc2018_it").mkdir()
    (tmp_path / "clc2018_it" / "clc2018_it_100m.tif").write_bytes(b"TIF")

    scaricati, falliti = await dati_base.sync_dati_base(idrogeo, tmp_path)
    assert falliti == {}
    # Il raster CORINE c'era già: non si rifà.
    assert scaricati == ["confini ISTAT", "CORINE 2018", "DTM 5 m", "geolitologia"]
    assert (tmp_path / "dtm" / "HRDTM5m_v1.3.tif").read_bytes() == _DTM

    # ISTAT: una cartella sola, non Limiti01012023_g/Limiti01012023_g.
    com = tmp_path / "Limiti01012023_g" / "Com01012023_g" / "Com01012023_g_WGS84.shp"
    assert com.read_bytes() == b"SHP"
    assert not list(tmp_path.glob("Limiti01012023_g.zip*"))
    # CORINE: i cinque file dello shapefile, accanto al raster che c'era.
    clc = tmp_path / "clc2018_it"
    assert (clc / "CLC18_IT.dbf").read_bytes() == b"dbf"
    assert (clc / "clc2018_it_100m.tif").read_bytes() == b"TIF"
    # Geolitologia: shapefile con gli assi raddrizzati, senza il GML e il .gfs.
    geo = tmp_path / "carta_geolitologica"
    assert sorted(p.suffix for p in geo.iterdir()) == [".cpg", ".dbf", ".prj", ".shp", ".shx"]
    import pyogrio

    tabella = pyogrio.read_dataframe(geo / "carta_geolitologica.shp")
    assert list(tabella.legenda_li) == ["argille", "calcari"]
    assert "lowerCorner" not in tabella.columns
    minx, miny, maxx, maxy = tabella.total_bounds
    assert (minx, miny, maxx, maxy) == (9, 40, 16, 45)  # lon prima, lat dopo
    assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob("*.old"))

    finte.richieste.clear()
    assert await dati_base.sync_dati_base(idrogeo, tmp_path) == ([], {})
    assert finte.richieste == []


async def test_un_wfs_che_rifiuta_non_lascia_niente(
    fonti: tuple[_Fonti, IdroGEO], tmp_path: Path
) -> None:
    finte, _ = fonti
    finte.gml = b"<ows:ExceptionReport>msWFSGetFeature(): troppi oggetti</ows:ExceptionReport>"
    with pytest.raises(RuntimeError, match="troppi oggetti"):
        await dati_base.geolitologia(tmp_path)
    assert not (tmp_path / "carta_geolitologica").exists()


async def test_coordinate_fuori_dall_italia_si_rifiutano(
    fonti: tuple[_Fonti, IdroGEO], tmp_path: Path
) -> None:
    finte, _ = fonti
    finte.gml = _GML.replace(
        b"40 15 40 16 41 16 41 15 40 15", b"-40 15 -40 16 -41 16 -41 15 -40 15"
    )
    with pytest.raises(RuntimeError, match="fuori dall'Italia"):
        await dati_base.geolitologia(tmp_path)
    assert not list(tmp_path.iterdir())


async def test_un_dataset_che_non_arriva_non_ferma_gli_altri(
    fonti: tuple[_Fonti, IdroGEO], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, idrogeo = fonti

    async def rotto(*_a: object) -> bool:
        raise httpx.ConnectError("giù")

    monkeypatch.setattr(dati_base, "istat", rotto)
    monkeypatch.setattr(dati_base, "corine_raster", lambda _d: rotto())
    monkeypatch.setattr(dati_base, "dtm", lambda _d: rotto())
    scaricati, falliti = await dati_base.sync_dati_base(idrogeo, tmp_path)
    assert scaricati == ["CORINE 2018", "geolitologia"]
    assert list(falliti) == ["confini ISTAT", "raster CORINE", "DTM 5 m"]


async def test_il_dtm_riprende_da_dove_si_era_fermato(
    fonti: tuple[_Fonti, IdroGEO], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    finte, _ = fonti
    monkeypatch.delenv("LIMEN_DEM_RASTER", raising=False)
    finte.taglia_dopo = 3000  # la connessione cade a 3000 byte
    assert await dati_base.dtm(tmp_path)
    assert (tmp_path / "dtm" / "HRDTM5m_v1.3.tif").read_bytes() == _DTM
    scaricati = [r for r in finte.richieste if r.url.path.endswith("/content")]
    assert [r.headers.get("range") for r in scaricati] == [None, "bytes=3000-"]


async def test_un_dtm_con_md5_sbagliato_non_si_tiene(
    fonti: tuple[_Fonti, IdroGEO], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    finte, _ = fonti
    monkeypatch.delenv("LIMEN_DEM_RASTER", raising=False)
    finte.md5 = "0" * 32
    with pytest.raises(RuntimeError, match="md5"):
        await dati_base.dtm(tmp_path)
    assert not list((tmp_path / "dtm").iterdir())


async def test_il_dtm_gia_configurato_non_si_scarica(
    fonti: tuple[_Fonti, IdroGEO], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    finte, _ = fonti
    esistente = tmp_path / "hrdtm5m.tif"
    esistente.write_bytes(b"DTM")
    monkeypatch.setenv("LIMEN_DEM_RASTER", str(esistente))
    assert not await dati_base.dtm(tmp_path)
    assert finte.richieste == []


async def test_senza_spazio_il_dtm_non_parte(
    fonti: tuple[_Fonti, IdroGEO], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    finte, _ = fonti
    monkeypatch.delenv("LIMEN_DEM_RASTER", raising=False)
    monkeypatch.setattr(dati_base, "_DTM_MARGINE_BYTE", 10**18)
    with pytest.raises(RuntimeError, match="servono"):
        await dati_base.dtm(tmp_path)
    assert [r.url.path for r in finte.richieste] == ["/api/records/24009736"]


async def test_il_raster_corine_dallo_shapefile(tmp_path: Path) -> None:
    import geopandas as gpd
    import rasterio
    from shapely.geometry import box

    cartella = tmp_path / "clc2018_it"
    cartella.mkdir()
    # Due poligoni in UTM 32N, 300 x 200 m: due classi CORINE vicine.
    gpd.GeoDataFrame(
        {"CODE_18": ["311", "112"]},
        geometry=[
            box(500_000, 4_500_000, 500_300, 4_500_200),
            box(500_300, 4_500_000, 500_600, 4_500_200),
        ],
        crs=32632,
    ).to_file(cartella / "CLC18_IT.shp")
    assert await dati_base.corine_raster(tmp_path)
    with rasterio.open(cartella / "clc2018_it_100m.tif") as r:
        # La griglia di gdal_rasterize: mezzo pixel in più per lato.
        assert (r.width, r.height) == (7, 3)
        assert (r.transform.c, r.transform.f) == (499_950, 4_500_250)
        banda = r.read(1)
    # Un centro di pixel sul bordo segue la regola di GDAL (qui: il bordo
    # sinistro resta fuori, quello in comune va al primo poligono): sul raster
    # dell'Italia il risultato è identico pixel per pixel a gdal_rasterize.
    assert banda.tolist() == [[0, 311, 311, 311, 112, 112, 112]] * 3
    assert not await dati_base.corine_raster(tmp_path)  # già fatto


async def test_corine_interrotto_non_lascia_shapefile_a_meta(tmp_path: Path) -> None:
    finte = _Fonti()

    def cade_sul_dbf(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".dbf"):
            raise httpx.ConnectError("giù", request=request)
        return finte(request)

    idrogeo = IdroGEO(httpx.AsyncClient(transport=httpx.MockTransport(cade_sul_dbf)), retries=0)
    with pytest.raises(httpx.ConnectError):
        await dati_base.corine(idrogeo, tmp_path)
    assert list(tmp_path.iterdir()) == []


async def test_istat_rotto_si_riscarica(tmp_path: Path) -> None:
    def zip_rotto(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"non e' uno zip", headers={"ETag": '"x"'})

    idrogeo = IdroGEO(httpx.AsyncClient(transport=httpx.MockTransport(zip_rotto)), retries=0)
    with pytest.raises(zipfile.BadZipFile):
        await dati_base.istat(idrogeo, tmp_path)
    # Né lo ZIP né il suo ETag: il prossimo giro lo riscarica invece di un 304.
    assert list(tmp_path.iterdir()) == []


def test_gli_appoggi_di_un_giro_interrotto_si_tolgono(tmp_path: Path) -> None:
    for nome in ("clc2018_it.part", "Limiti01012023_g.zip.d", "carta_geolitologica.old"):
        (tmp_path / nome).mkdir()
        (tmp_path / nome / "x.shp").write_bytes(b"")
    (tmp_path / "dtm").mkdir()
    (tmp_path / "dtm" / "HRDTM5m_v1.3.tif.part").write_bytes(b"ripresa")
    (tmp_path / "clc2018_it").mkdir()
    assert sorted(dati_base.pulisci_appoggi(tmp_path)) == [
        "Limiti01012023_g.zip.d",
        "carta_geolitologica.old",
        "clc2018_it.part",
    ]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clc2018_it", "dtm"]
    assert (tmp_path / "dtm" / "HRDTM5m_v1.3.tif.part").exists()
