"""Il resto del PostGIS di GeoServer: confini ISTAT, CORINE 2018, geolitologia.

Con l'inventario IFFI e i mosaici di ``idrogeo.geodati`` sono tutto quello che
``geoserver-init`` carica, quindi un server nuovo ricostruisce quel database
da fonti pubbliche, senza account:

* **confini amministrativi ISTAT 2023** (comuni, province, regioni,
  ripartizioni), lo ZIP ufficiale. ``seed-comuni`` e il nome del comune nelle
  allerte leggono ``com01012023_g``;
* **CORINE Land Cover 2018** (``CLC18_IT``), lo shapefile che SINAnet ISPRA
  pubblica un file alla volta. Alla HEAD risponde 404, al GET no;
* **Carta geolitologica d'Italia 1:500.000** dal WFS del Geoportale
  Nazionale (MASE), che parla solo GML e scrive le coordinate lat/lon: si
  scarica con ``fetch_with_retry`` e si converte qui in shapefile, con gli
  assi raddrizzati. Leggerlo con il driver WFS di GDAL avrebbe portato la
  richiesta fuori da ``_http``.

Sono dataset con l'anno nel nome e non cambiano: uno già sul disco non si
richiede.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from functools import partial
from pathlib import Path

import httpx
from ispra_idrogeo import Dataset, IdroGEO, extract
from ispra_idrogeo.cache import meta_path

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry, fetch_with_retry

log = get_logger(__name__)

ISTAT = Dataset(
    url=(
        "https://www.istat.it/storage/cartografia/confini_amministrativi/"
        "generalizzati/2023/Limiti01012023_g.zip"
    ),
    filename="Limiti01012023_g.zip",
)

_CORINE_URL = (
    "https://groupware.sinanet.isprambiente.it/uso-copertura-e-consumo-di-suolo/"
    "library/copertura-del-suolo/corine-land-cover/clc2018_shapefile"
)
CORINE_CARTELLA = "clc2018_it"
#: Il raster per cella che `bootstrap-static` legge (LIMEN_CORINE_RASTER):
#: CODE_18 a 100 m, come lo faceva `gdal_rasterize -tr 100 100`.
CORINE_RASTER = "clc2018_it_100m.tif"
_CORINE_PASSO_M = 100.0
CORINE: tuple[Dataset, ...] = tuple(
    Dataset(url=f"{_CORINE_URL}/{voce}/download/en/1/CLC18_IT.{ext}", filename=f"CLC18_IT.{ext}")
    for voce, ext in (
        ("clc18_it-2", "shp"),
        ("clc18_it-4", "shx"),
        ("clc18_it-5", "dbf"),
        ("clc18_it-3", "prj"),
        ("clc18_it-1", "cpg"),
    )
)

GEOLITOLOGIA_URL = "http://wms.pcn.minambiente.it/ogc"
GEOLITOLOGIA_PARAMETRI = {
    "map": "/ms_ogc/wfs/Carta_geolitologica.map",
    "service": "WFS",
    "version": "1.1.0",
    "request": "GetFeature",
    "typeName": "GE.CARTAGEOLITOLOGICA",
}
GEOLITOLOGIA_CARTELLA = "carta_geolitologica"
#: Il GML risponde in ~30 s (26 MB): il timeout di lettura del client
#: condiviso (60 s) basta, ma non con margine.
_TIMEOUT_GEOLITOLOGIA_S = 180.0
#: Campi che il GML aggiunge e lo shapefile di riferimento non ha (``gml_id``
#: invece sì: lo shapefile in uso è uscito dallo stesso WFS con ogr2ogr).
_CAMPI_GML = ("lowerCorner", "upperCorner")


#: HR-DTM 5 m di IRPI-CNR (Panza et al.), CC BY 4.0: il record Zenodo della
#: versione 1.3, fissato perché un DTM nuovo cambia la pendenza per cella e va
#: scelto, non preso da sé (#468: 0,4 % delle celle oltre 2° dalla 1.2, quasi
#: tutte artefatti corretti). Il nome locale porta la versione: un file nuovo
#: si scarica accanto al vecchio, e il bootstrap lo vede come sorgente nuova.
DTM_RECORD = "https://zenodo.org/api/records/24009736"
DTM_CARTELLA = "dtm"
DTM_FILE = "HRDTM5m_v1.3.tif"
#: Spazio libero da lasciare oltre al file, per non riempire il disco.
_DTM_MARGINE_BYTE = 5 * 10**9
_BLOCCO = 1 << 20


async def istat(idrogeo: IdroGEO, dove: Path) -> bool:
    """I confini ISTAT in ``dove/Limiti01012023_g``; ``True`` se scaricati ora."""
    finale = dove / ISTAT.stem
    if finale.is_dir():
        return False
    scaricato = await call_with_retry(lambda: idrogeo.download(ISTAT, dove))
    # Lo ZIP ha già la sua cartella in cima: si estrae a parte e la si sposta,
    # o finirebbe in Limiti01012023_g/Limiti01012023_g.
    appoggio = dove / f"{ISTAT.stem}.zip.d"
    try:
        await asyncio.to_thread(extract, scaricato.path, appoggio)
        await asyncio.to_thread(_sposta, appoggio / ISTAT.stem, finale)
    finally:
        # Anche se fallisce: uno ZIP rotto con il suo ETag riceverebbe 304 per
        # sempre, e la cartella d'appoggio geoserver-init la caricherebbe.
        shutil.rmtree(appoggio, ignore_errors=True)
        scaricato.path.unlink(missing_ok=True)
        meta_path(scaricato.path).unlink(missing_ok=True)
    return True


async def corine(idrogeo: IdroGEO, dove: Path) -> bool:
    """Lo shapefile CORINE in ``dove/clc2018_it``; ``True`` se scaricato ora."""
    cartella = dove / CORINE_CARTELLA
    if all((cartella / ds.filename).exists() for ds in CORINE):
        return False
    appoggio = dove / f"{CORINE_CARTELLA}.part"
    appoggio.mkdir(parents=True, exist_ok=True)
    try:
        for ds in CORINE:
            await call_with_retry(partial(idrogeo.download, ds, appoggio))
        # I file del raster per cella (`clc2018_it_100m.tif`) stanno nella
        # stessa cartella: si aggiungono i file dello shapefile, non si
        # sostituisce la cartella.
        cartella.mkdir(parents=True, exist_ok=True)
        for ds in CORINE:
            (appoggio / ds.filename).replace(cartella / ds.filename)
    finally:
        # Un CLC18_IT.shp a metà lasciato qui diventerebbe una tabella
        # `clc2018_it_part` in PostGIS, che geoserver-init non toglie più.
        shutil.rmtree(appoggio, ignore_errors=True)
    return True


async def corine_raster(dove: Path) -> bool:
    """Il raster CORINE per cella dallo shapefile; ``True`` se scritto ora."""
    cartella = dove / CORINE_CARTELLA
    tif = cartella / CORINE_RASTER
    shp = cartella / "CLC18_IT.shp"
    if tif.exists() or not shp.exists():
        return False
    await asyncio.to_thread(_rasterizza_corine, shp, tif)
    return True


def _rasterizza_corine(shp: Path, tif: Path) -> None:
    import pyogrio
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    tabella = pyogrio.read_dataframe(shp, columns=["CODE_18"])
    passo = _CORINE_PASSO_M
    # La griglia di gdal_rasterize con -tr: il riquadro allargato di mezzo
    # pixel per lato e il numero di pixel arrotondato. Così il raster coincide
    # con quello costruito a mano (verificato pixel per pixel sull'Italia).
    x0, y0, x1, y1 = tabella.total_bounds
    x0, y0, x1, y1 = x0 - passo / 2, y0 - passo / 2, x1 + passo / 2, y1 + passo / 2
    larghezza = int(0.5 + (x1 - x0) / passo)
    altezza = int(0.5 + (y1 - y0) / passo)
    trasformata = from_origin(x0, y1, passo, passo)
    codici = tabella["CODE_18"].astype(int)
    banda = rasterize(
        zip(tabella.geometry.values, codici, strict=True),
        out_shape=(altezza, larghezza),
        transform=trasformata,
        fill=0,
        dtype="int16",
    )
    parziale = tif.with_name(f"{tif.name}.part")
    with rasterio.open(
        parziale,
        "w",
        driver="GTiff",
        width=larghezza,
        height=altezza,
        count=1,
        dtype="int16",
        crs=tabella.crs,
        transform=trasformata,
        nodata=0,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
    ) as uscita:
        uscita.write(banda, 1)
    parziale.replace(tif)


async def geolitologia(dove: Path) -> bool:
    """La carta geolitologica in ``dove/carta_geolitologica``; ``True`` se scaricata ora."""
    finale = dove / GEOLITOLOGIA_CARTELLA
    if (finale / f"{GEOLITOLOGIA_CARTELLA}.shp").exists():
        return False
    resp = await fetch_with_retry(
        "GET", GEOLITOLOGIA_URL, params=GEOLITOLOGIA_PARAMETRI, timeout=_TIMEOUT_GEOLITOLOGIA_S
    )
    resp.raise_for_status()
    if b"ExceptionReport" in resp.content[:2000]:
        raise RuntimeError(f"WFS geolitologia: {resp.text[:300]}")
    appoggio = dove / f"{GEOLITOLOGIA_CARTELLA}.part"
    shutil.rmtree(appoggio, ignore_errors=True)
    appoggio.mkdir(parents=True)
    gml = appoggio / "sorgente.gml"
    gml.write_bytes(resp.content)
    try:
        await asyncio.to_thread(_gml_a_shapefile, gml, appoggio / f"{GEOLITOLOGIA_CARTELLA}.shp")
        gml.unlink()
        # Il .gfs è lo schema che GDAL deduce dal GML: geoserver-init non lo usa.
        gml.with_suffix(".gfs").unlink(missing_ok=True)
        await asyncio.to_thread(_sposta, appoggio, finale)
    except BaseException:
        shutil.rmtree(appoggio, ignore_errors=True)
        raise
    return True


async def dtm(dove: Path) -> bool:
    """Il DTM a 5 m in ``dove/dtm/HRDTM5m_v1.3.tif``; ``True`` se scaricato ora.

    Niente da fare se ``LIMEN_DEM_RASTER`` punta già a un file che esiste (il
    server di oggi usa una copia rielaborata dello stesso DTM). Sono 34 GB:
    un errore di rete riprende dal ``.part`` invece che da zero, e il file si
    rinomina solo dopo aver controllato dimensione e md5 dichiarati da Zenodo.
    """
    configurato = os.environ.get("LIMEN_DEM_RASTER", "").strip()
    if configurato and Path(configurato).exists():
        return False
    finale = dove / DTM_CARTELLA / DTM_FILE
    if finale.exists():
        return False
    resp = await fetch_with_retry("GET", DTM_RECORD)
    resp.raise_for_status()
    # Il record ha anche la maschera delle fonti (.gpkg): serve il raster.
    (voce,) = [f for f in resp.json()["files"] if str(f["key"]).endswith(".tif")]
    url = str(voce["links"]["self"])
    dimensione = int(voce["size"])
    md5 = str(voce["checksum"]).removeprefix("md5:")
    finale.parent.mkdir(parents=True, exist_ok=True)
    parziale = finale.with_name(f"{finale.name}.part")
    gia = parziale.stat().st_size if parziale.exists() else 0
    libero = shutil.disk_usage(finale.parent).free
    servono = dimensione - gia + _DTM_MARGINE_BYTE
    if libero < servono:
        raise RuntimeError(
            f"DTM: servono {servono / 1e9:.1f} GB in {finale.parent} "
            f"(margine compreso), liberi {libero / 1e9:.1f}"
        )
    log.info("geodati.dtm_inizio", gb=round(dimensione / 1e9, 1), ripresa_gb=round(gia / 1e9, 1))
    await call_with_retry(partial(_scarica_riprendendo, url, parziale, dimensione))
    if await asyncio.to_thread(_md5, parziale) != md5:
        # Un file sbagliato ripreso all'infinito non diventerebbe mai giusto.
        parziale.unlink()
        raise RuntimeError("DTM: md5 diverso da quello dichiarato da Zenodo, riscaricare")
    parziale.replace(finale)
    return True


async def _scarica_riprendendo(url: str, parziale: Path, dimensione: int) -> None:
    client = await SharedHttpClient.get()
    gia = parziale.stat().st_size if parziale.exists() else 0
    if gia >= dimensione:
        return
    intestazioni = {"Range": f"bytes={gia}-"} if gia else {}
    async with client.stream("GET", url, headers=intestazioni) as risposta:
        risposta.raise_for_status()
        if gia and risposta.status_code != 206:
            gia = 0  # il server ignora il Range: si riparte
        with parziale.open("ab" if gia else "wb") as uscita:
            async for blocco in risposta.aiter_bytes(_BLOCCO):
                # Fuori dal loop: lo condivide lo sweep orario del worker.
                await asyncio.to_thread(uscita.write, blocco)
    if parziale.stat().st_size != dimensione:
        raise httpx.ReadError(f"DTM interrotto a {parziale.stat().st_size} di {dimensione} byte")


def _md5(path: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        for blocco in iter(lambda: f.read(_BLOCCO), b""):
            h.update(blocco)
    return h.hexdigest()


def _gml_a_shapefile(gml: Path, shp: Path) -> int:
    import pyogrio
    from shapely import transform

    # Senza, GDAL scaricherebbe lo schema XSD dal server: rete fuori da _http.
    # L'opzione è del processo: si rimette com'era.
    prima = pyogrio.get_gdal_config_option("GML_DOWNLOAD_WFS_SCHEMA")
    pyogrio.set_gdal_config_options({"GML_DOWNLOAD_WFS_SCHEMA": "NO"})
    try:
        tabella = pyogrio.read_dataframe(gml)
    finally:
        pyogrio.set_gdal_config_options({"GML_DOWNLOAD_WFS_SCHEMA": prima})
    tabella = tabella.drop(columns=[c for c in _CAMPI_GML if c in tabella.columns])
    minx, miny, _, _ = tabella.total_bounds
    # WFS 1.1 in EPSG:4326 è lat/lon. Si raddrizza solo se serve: se un giorno
    # il servizio lo corregge, invertire di nuovo metterebbe l'Italia nel Corno
    # d'Africa senza nessun errore.
    if minx > miny:
        tabella = tabella.set_geometry(transform(tabella.geometry.values, lambda xy: xy[:, ::-1]))
    tabella = tabella.set_crs(4326, allow_override=True)
    minx, miny, maxx, maxy = tabella.total_bounds
    if not (5 < minx < maxx < 20 and 35 < miny < maxy < 48):
        raise RuntimeError(f"geolitologia fuori dall'Italia: {tabella.total_bounds}")
    pyogrio.write_dataframe(tabella, shp)
    return len(tabella)


def _sposta(sorgente: Path, finale: Path) -> None:
    vecchia = finale.with_name(f"{finale.name}.old")
    shutil.rmtree(vecchia, ignore_errors=True)
    if finale.exists():
        finale.rename(vecchia)
    sorgente.rename(finale)
    shutil.rmtree(vecchia, ignore_errors=True)


#: Le cartelle d'appoggio di questo modulo e di ispra-idrogeo.
_APPOGGI = (".part", ".zip.d", ".old")


def pulisci_appoggi(dove: Path) -> list[str]:
    """Toglie le cartelle d'appoggio rimaste da un giro interrotto.

    geoserver-init carica ogni ``*.shp`` sotto la cartella e chiama il layer
    come la cartella che lo contiene: un ``clc2018_it.part`` dimenticato
    diventerebbe una tabella in PostGIS. Solo cartelle in cima: il
    ``HRDTM5m_v1.3.tif.part`` del DTM è un file in ``dtm/`` e serve alla ripresa.
    """
    tolte = []
    for voce in dove.iterdir() if dove.is_dir() else ():
        if voce.is_dir() and voce.name.endswith(_APPOGGI):
            shutil.rmtree(voce, ignore_errors=True)
            tolte.append(voce.name)
    if tolte:
        log.info("geodati.appoggi_tolti", cartelle=tolte)
    return tolte


async def sync_dati_base(idrogeo: IdroGEO, dove: Path) -> tuple[list[str], dict[str, str]]:
    """Scarica i dataset che mancano; (scaricati ora, falliti con il motivo)."""
    scaricati: list[str] = []
    falliti: dict[str, str] = {}
    passi = (
        ("confini ISTAT", istat(idrogeo, dove)),
        ("CORINE 2018", corine(idrogeo, dove)),
        ("raster CORINE", corine_raster(dove)),
        ("DTM 5 m", dtm(dove)),
        ("geolitologia", geolitologia(dove)),
    )
    for nome, passo in passi:
        try:
            if await passo:
                scaricati.append(nome)
                log.info("geodati.base_scaricato", dataset=nome)
        except Exception as exc:  # uno che non arriva non ferma gli altri
            log.warning("geodati.base_fallito", dataset=nome, error=str(exc)[:300])
            falliti[nome] = str(exc)[:300]
    return scaricati, falliti


__all__ = [
    "CORINE",
    "GEOLITOLOGIA_PARAMETRI",
    "ISTAT",
    "corine",
    "corine_raster",
    "dtm",
    "geolitologia",
    "istat",
    "pulisci_appoggi",
    "sync_dati_base",
]
