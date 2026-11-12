"""Soil Water Index 1 km di Copernicus Land, letto a pixel dall'archivio CDSE (#507).

L'SWI (``c_gls_SWI1km``, ASCAT + Sentinel-1, Europa a 1 km) è l'umidità della
zona radicale stimata ogni giorno dal 2015, in percentuale di saturazione. Per
ogni giorno c'è una cartella COG con un file per ogni «tempo caratteristico»
``T`` (``SWI002`` … ``SWI100``: più è lungo, più lo strato è profondo e lenta
la risposta alla pioggia).

Il nome del file porta la versione del prodotto (``V1.0.1``, ``V1.0.2``,
``V2.1.1`` …) e la collezione cambia (``swi_europe_1km_daily_v1`` e ``_v2``),
quindi non si ricostruisce: si **elenca** la cartella del giorno con
``ListObjectsV2`` sull'S3 del CDSE, firmato SigV4 e passato da
``fetch_with_retry`` come ogni chiamata in uscita. Si preferisce la v1 dove
esiste, per non cambiare versione dentro una misura.

Il pixel si legge con rasterio da ``/vsis3/``: GDAL chiede solo i byte delle
tessere che servono, invece dei ~7 MB del file. È l'unico passo che non passa
da ``_http`` (lo stack HTTP è quello di GDAL, con i suoi tentativi a zero):
come le altre librerie dell'elenco di CLAUDE.md, l'errore torna qui e diventa
``None`` con ``integration.degraded``.

Sola lettura; senza chiavi S3 (``COPERNICUS__CDSE_S3_*``) non si legge niente.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

HOST = "eodata.dataspace.copernicus.eu"
BUCKET = "eodata"
_REGIONE = "default"
_RADICE = "CLMS/bio-geophysical/soil_water_index"
COLLEZIONI = ("swi_europe_1km_daily_v1", "swi_europe_1km_daily_v2")
ATTRIBUZIONE = "Copernicus Land Monitoring Service, Soil Water Index 1 km (SCATSAR)"
_CHIAVE = re.compile(r"<Key>([^<]+)</Key>")


@dataclass(frozen=True, slots=True)
class Chiavi:
    accesso: str
    segreto: str


def _firma(chiavi: Chiavi, query: str, ora: datetime) -> dict[str, str]:
    """Le intestazioni SigV4 di un GET sul bucket (path-style, corpo vuoto)."""
    amz = ora.strftime("%Y%m%dT%H%M%SZ")
    giorno = ora.strftime("%Y%m%d")
    vuoto = hashlib.sha256(b"").hexdigest()
    canonica = (
        f"GET\n/{BUCKET}\n{query}\nhost:{HOST}\nx-amz-content-sha256:{vuoto}\n"
        f"x-amz-date:{amz}\n\nhost;x-amz-content-sha256;x-amz-date\n{vuoto}"
    )
    ambito = f"{giorno}/{_REGIONE}/s3/aws4_request"
    da_firmare = (
        f"AWS4-HMAC-SHA256\n{amz}\n{ambito}\n{hashlib.sha256(canonica.encode()).hexdigest()}"
    )
    k = ("AWS4" + chiavi.segreto).encode()
    for parte in (giorno, _REGIONE, "s3", "aws4_request"):
        k = hmac.new(k, parte.encode(), hashlib.sha256).digest()
    firma = hmac.new(k, da_firmare.encode(), hashlib.sha256).hexdigest()
    return {
        "x-amz-date": amz,
        "x-amz-content-sha256": vuoto,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={chiavi.accesso}/{ambito}, "
            f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature={firma}"
        ),
    }


async def elenca(prefisso: str, chiavi: Chiavi) -> list[str]:
    """Le chiavi S3 sotto ``prefisso`` (fino a 1000: una cartella del giorno ne ha ~20)."""
    query = urlencode(
        sorted({"list-type": "2", "prefix": prefisso, "max-keys": "1000"}.items()),
        quote_via=quote,
    )
    resp = await fetch_with_retry(
        "GET",
        f"https://{HOST}/{BUCKET}?{query}",
        client=await SharedHttpClient.get(),
        headers=_firma(chiavi, query, datetime.now(UTC)),
    )
    resp.raise_for_status()
    return _CHIAVE.findall(resp.text)


def scegli(chiavi_s3: Sequence[str], t: str) -> str | None:
    """Il file COG dell'SWI con tempo caratteristico ``t`` (es. ``"020"``)."""
    for k in sorted(chiavi_s3):
        if "_cog/" in k and f"-SWI{t}_" in k and k.endswith((".tif", ".tiff")):
            return k
    return None


async def file_del_giorno(giorno: date, t: str, chiavi: Chiavi) -> str | None:
    """La chiave S3 del file SWI di ``giorno`` (etichetta 12:00 UTC), o ``None``."""
    for collezione in COLLEZIONI:
        prefisso = f"{_RADICE}/{collezione}/{giorno:%Y/%m/%d}/"
        trovato = scegli(await elenca(prefisso, chiavi), t)
        if trovato is not None:
            return trovato
    return None


def leggi_pixel(
    chiave_s3: str, punti: Sequence[tuple[float, float]], chiavi: Chiavi
) -> list[float | None]:
    """L'SWI (% di saturazione) ai ``punti`` ``(lon, lat)``; ``None`` dove non c'è."""
    import rasterio  # gruppo geo: import locale come per gli altri raster

    # rasterio rifiuta le opzioni AWS_* nel suo Env (le vorrebbe da boto3, che
    # qui non entra), GDAL le legge dall'ambiente del processo: è il processo di
    # un comando di misura, e sono le stesse chiavi per ogni lettura.
    os.environ["AWS_ACCESS_KEY_ID"] = chiavi.accesso
    os.environ["AWS_SECRET_ACCESS_KEY"] = chiavi.segreto
    with (
        rasterio.Env(
            AWS_S3_ENDPOINT=HOST,
            AWS_VIRTUAL_HOSTING="FALSE",
            AWS_REGION=_REGIONE,
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
            GDAL_HTTP_MAX_RETRY="0",
        ),
        rasterio.open(f"/vsis3/{BUCKET}/{chiave_s3}") as ds,
    ):
        scala = ds.scales[0] if ds.scales else 1.0
        scarto = ds.offsets[0] if ds.offsets else 0.0
        out: list[float | None] = []
        for lon, lat in punti:
            riga, colonna = ds.index(lon, lat)
            finestra = ds.read(1, window=((riga - 1, riga + 2), (colonna - 1, colonna + 2)))
            out.append(valore_del_punto(finestra, ds.nodata, scala, scarto))
        return out


def valore_del_punto(
    finestra: Any, nodata: float | None, scala: float, scarto: float
) -> float | None:
    """Il pixel centrale se valido, altrimenti la mediana dei validi del 3x3.

    L'SWI maschera molti versanti: al punto esatto di una frana c'è un valore
    in un caso su tre, entro un chilometro in poco più di uno su due (misurato
    su 300 frane, 12/11/2026). Fuori dal 3x3 il dato non è più di quel punto.
    """
    import numpy as np

    valori = np.asarray(finestra, dtype=float)
    validi = valori if nodata is None else valori[valori != nodata]
    if validi.size == 0:
        return None
    centro = valori[1, 1] if valori.shape == (3, 3) else None
    grezzo = (
        float(centro)
        if centro is not None and (nodata is None or centro != nodata)
        else float(np.median(validi))
    )
    return grezzo * scala + scarto


async def swi(
    punti_per_giorno: dict[date, list[tuple[float, float]]],
    *,
    t: str,
    chiavi: Chiavi,
    concorrenza: int = 8,
) -> dict[date, list[float | None]]:
    """L'SWI di ogni giorno ai suoi punti. Un giorno senza file o illeggibile è tutto ``None``."""
    limite = asyncio.Semaphore(concorrenza)

    async def uno(giorno: date, punti: list[tuple[float, float]]) -> list[float | None]:
        vuoto: list[float | None] = [None] * len(punti)
        async with limite:
            try:
                chiave = await file_del_giorno(giorno, t, chiavi)
                if chiave is None:
                    return vuoto
                return await asyncio.to_thread(leggi_pixel, chiave, punti, chiavi)
            except (httpx.HTTPError, OSError) as exc:
                # RasterioIOError è un OSError.
                log.warning(
                    "integration.degraded",
                    source="copernicus_land_swi",
                    giorno=str(giorno),
                    error=str(exc)[:200],
                )
                return vuoto

    giorni = sorted(punti_per_giorno)
    valori = await asyncio.gather(*(uno(g, punti_per_giorno[g]) for g in giorni))
    return dict(zip(giorni, valori, strict=True))
