"""Unit checks for the DPC radar client: grid sampling, cache, HTTP paths."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pytest
import rasterio
from dpc_radar import ABSENT, DpcRadarError, RainGrid
from rasterio.io import MemoryFile

from limen.integrations import _http
from limen.integrations.dpc import client

_T = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
_TRANSFORM = rasterio.Affine(0.1, 0, 10.0, 0, -0.1, 45.0)


def _data() -> np.ndarray:
    """10x10 over lon 10→11, lat 44→45 (0.1° pixels)."""
    data = np.full((10, 10), 0.5, dtype=np.float32)
    data[2:4, 3:6] = 35.0  # convective blob: 6 hot pixels
    data[0, 0] = -9999.0  # nodata sentinel
    return data


def _tiff(data: np.ndarray) -> bytes:
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=_TRANSFORM,
            nodata=-9999.0,
        ) as ds:
            ds.write(data, 1)
        return bytes(mem.read())


def _grid(data: np.ndarray | None = None, time: datetime = _T) -> RainGrid:
    return RainGrid.from_geotiff(_tiff(_data() if data is None else data), "CUM24", time)


def test_blob_detected_inside_bbox() -> None:
    peak, hot = _grid().peak((10.0, 44.0, 11.0, 45.0), threshold=30.0)
    assert peak == 35.0
    assert hot == 6


def test_quiet_bbox_has_no_trigger() -> None:
    peak, hot = _grid().peak((10.0, 44.0, 10.2, 44.2), threshold=30.0)
    assert peak == 0.5
    assert hot == 0


def test_out_of_coverage_returns_zero() -> None:
    assert _grid().peak((20.0, 50.0, 21.0, 51.0), threshold=30.0) == (0.0, 0)


def test_nodata_is_ignored() -> None:
    peak, _ = _grid().peak((10.0, 44.8, 10.2, 45.0), threshold=30.0)
    assert peak >= 0.0


def test_sample_reads_the_median_of_the_window_not_the_pixel() -> None:
    """Un pixel spurio non allaga una cella (#199)."""
    data = _data()
    data[7, 7] = 7348.0
    centro = (10.75, 44.25)  # pixel (7, 7)
    blob = (10.45, 44.75)  # pixel (2, 4), dentro il blob
    assert _grid(data).sample([centro, blob]) == [0.5, 35.0]


def test_sample_outside_or_on_nodata_is_not_measured() -> None:
    data = _data()
    data[:3, :3] = -9999.0
    assert _grid(data).sample([(20.0, 50.0), (10.05, 44.95)]) == [None, None]
    assert _grid().sample([]) == []


def _old_sample(data: np.ndarray, points: list[tuple[float, float]]) -> list[float | None]:
    """Il campionamento di Limen prima di dpc-radar (`SriGrid.sample`), su float32 e -9999."""
    rows, cols = rasterio.transform.rowcol(
        _TRANSFORM, [p[0] for p in points], [p[1] for p in points]
    )
    out: list[float | None] = []
    for r, c in zip(rows, cols, strict=True):
        if not (0 <= r < data.shape[0] and 0 <= c < data.shape[1]):
            out.append(None)
            continue
        tile = data[max(0, r - 1) : r + 2, max(0, c - 1) : c + 2]
        valid = tile[tile > -9999.0]
        out.append(float(np.median(valid)) if valid.size else None)
    return out


def test_parita_con_il_campionamento_di_prima() -> None:
    """Stesso fotogramma, stessi numeri: la mediana in float64 del pacchetto
    differisce da quella in float32 di prima solo per l'arrotondamento."""
    rng = np.random.default_rng(235)
    data = rng.gamma(0.6, 12.0, size=(10, 10)).astype(np.float32)
    data[rng.random((10, 10)) < 0.15] = -9999.0
    points = [(10.0 + 0.1 * i + 0.05, 44.0 + 0.1 * j + 0.05) for i in range(10) for j in range(10)]
    points.append((30.0, 50.0))
    old = _old_sample(data, points)
    new = _grid(data).sample(points)
    assert [o is None for o in old] == [n is None for n in new]
    assert (
        max(abs(o - n) for o, n in zip(old, new, strict=True) if o is not None and n is not None)
        < 1e-6
    )


async def test_a_cumulative_frame_is_downloaded_once_per_issue(monkeypatch: Any) -> None:
    """Venti regioni chiedono lo stesso file nazionale: si riscarica solo
    quando il DPC ne pubblica uno nuovo."""
    visti: list[RainGrid | None] = []

    async def _download(tipo: str, cached: RainGrid | None = None) -> RainGrid | None:
        assert tipo == "CUM24"
        visti.append(cached)
        return cached or _grid()

    monkeypatch.setattr(client, "_download", _download)
    monkeypatch.setattr(client, "_cum_cache", {})
    primo = await client.get_latest_cum(24)
    secondo = await client.get_latest_cum(24)
    assert visti == [None, primo]
    assert secondo is primo


async def test_il_precedente_arriva_dalla_cache_senza_scaricare(monkeypatch: Any) -> None:
    scaricati: list[object] = []
    vecchio = _grid()
    nuovo = _grid(time=_T + timedelta(minutes=30))
    sequenza = iter([vecchio, nuovo])

    async def _download(
        tipo: str, cached: RainGrid | None = None, *, at: object = None
    ) -> RainGrid | None:
        scaricati.append(at)
        return next(sequenza)

    monkeypatch.setattr(client, "_download", _download)
    monkeypatch.setattr(client, "_cum_cache", {})
    monkeypatch.setattr(client, "_cum_previous", {})
    await client.get_latest_cum(24)
    await client.get_latest_cum(24)
    assert await client.get_cum_at(24, vecchio.time) is vecchio
    assert scaricati == [None, None]


# --- HTTP: il client condiviso al posto della rete -------------------------

_LINK = "https://s3.example/frame.tif"
_S3_403 = "S3 error: Access Denied (Service: S3, Status Code: 403) Forbidden"


class _Rete:
    """Le risposte da dare per «METODO url», e le richieste arrivate."""

    def __init__(self) -> None:
        self.viste: list[httpx.Request] = []
        self.risposte: dict[str, httpx.Response] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.viste.append(request)
        return self.risposte[f"{request.method} {request.url.copy_with(query=None)}"]


_API = "https://radar-api.protezionecivile.it"


@pytest.fixture
def rete(monkeypatch: Any) -> _Rete:
    """Il client condiviso su una rete finta, e nessuna attesa vera nel backoff."""
    finta = _Rete()

    async def _subito(_: float) -> None:
        return None

    monkeypatch.setattr(
        _http.SharedHttpClient, "_instance", httpx.AsyncClient(transport=httpx.MockTransport(finta))
    )
    monkeypatch.setattr("asyncio.sleep", _subito)
    monkeypatch.setattr(client, "_cum_cache", {})
    monkeypatch.setattr(client, "_cum_previous", {})
    return finta


async def test_l_ultimo_fotogramma_passa_dal_client_condiviso(rete: _Rete) -> None:
    ms = int(_T.timestamp() * 1000)
    last = {"lastProducts": [{"productType": "CUM24", "time": ms, "period": "PT30M"}]}
    rete.risposte[f"GET {_API}/findLastProductByType"] = httpx.Response(200, json=last)
    rete.risposte[f"POST {_API}/downloadProduct"] = httpx.Response(200, json={"url": _LINK})
    rete.risposte[f"GET {_LINK}"] = httpx.Response(200, content=_tiff(_data()))

    grid = await client.get_latest_cum(24)
    assert grid is not None
    assert grid.time == _T
    assert grid.sample([(10.45, 44.75)]) == [35.0]
    assert rete.viste[0].headers["origin"] == "https://radar.protezionecivile.gov.it"
    assert json.loads(rete.viste[1].content) == {"productType": "CUM24", "productDate": ms}

    assert await client.get_latest_cum(24) is grid, "stesso fotogramma: niente download"
    assert len(rete.viste) == 4


async def test_un_fotogramma_scaduto_e_assente_con_una_richiesta_sola(
    rete: _Rete,
) -> None:
    """Il 500 con il 403 di S3 non si ritenta: ``ASSENTE`` subito (#429)."""
    rete.risposte[f"POST {_API}/downloadProduct"] = httpx.Response(500, text=_S3_403)
    radar = client.radar_archivio()
    assert await radar.download("CUM3", datetime(2026, 1, 1, tzinfo=UTC)) is ABSENT
    assert len(rete.viste) == 1


async def test_un_altro_errore_dell_archivio_e_un_errore_http(rete: _Rete) -> None:
    """Un ``httpx.HTTPError``: ``dpc_radar.archive`` lo conta fallito e lo ritenta."""
    rete.risposte[f"POST {_API}/downloadProduct"] = httpx.Response(502, text="Bad Gateway")
    with pytest.raises(httpx.HTTPError):
        await client.radar_archivio().download("CUM3", _T)
    assert len(rete.viste) == 1


async def test_una_risposta_non_json_e_un_fotogramma_fallito(rete: _Rete) -> None:
    """Un fotogramma che non si legge si conta e si ritenta: non ferma il giro."""
    rete.risposte[f"POST {_API}/downloadProduct"] = httpx.Response(200, text="<html>")
    with pytest.raises(DpcRadarError):
        await client.radar_archivio().download("CUM3", _T)


async def test_l_archivio_scarica_il_geotiff_com_e(rete: _Rete) -> None:
    raw = _tiff(_data())
    rete.risposte[f"POST {_API}/downloadProduct"] = httpx.Response(200, json={"url": _LINK})
    rete.risposte[f"GET {_LINK}"] = httpx.Response(200, content=raw)
    assert await client.radar_archivio().download("SRT1", _T) == raw


async def test_il_radar_che_non_risponde_degrada_a_none(rete: _Rete) -> None:
    rete.risposte[f"GET {_API}/findLastProductByType"] = httpx.Response(503)
    assert await client.get_latest_sri() is None
    assert len(rete.viste) == 4, "il 5xx si ritenta con la politica di _http"


async def test_nessun_prodotto_elencato_degrada_a_none(rete: _Rete) -> None:
    rete.risposte[f"GET {_API}/findLastProductByType"] = httpx.Response(
        200, json={"lastProducts": []}
    )
    assert await client.get_latest_sri() is None


# --- lo stato dei radar (dpc-radar 0.3) -------------------------------------

_STATO = "https://s3-prod-dpc-radar-webp-cache.s3.eu-south-1.amazonaws.com/SITES"


def _stato(spenti: tuple[str, ...]) -> dict[str, Any]:
    """Un file di stato fatto come quello del DPC, con due radar."""
    radar = [("LAURO", "Monte Lauro", 14.82, 37.12), ("LINATE", "Linate", 9.28, 45.34)]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "MultiPoint", "coordinates": [[lon, lat]]},
                "properties": {"nome": codice, "localita": luogo, "status": codice not in spenti},
            }
            for codice, luogo, lon, lat in radar
        ],
    }


async def test_lo_stato_dei_radar_a_un_ora(rete: _Rete) -> None:
    url = f"{_STATO}/2026/07/06/1200/sites.geojson"
    rete.risposte[f"GET {url}"] = httpx.Response(200, json=_stato(("LAURO",)))
    stato = await client.get_radar_status(_T)
    assert stato is not None and stato.time == _T
    assert [r.code for r in stato.off] == ["LAURO"]
    assert stato.of("Monte Lauro") is False and stato.of("LINATE") is True
    assert "origin" not in rete.viste[0].headers, "una richiesta semplice, senza intestazioni"


async def test_lo_stato_che_non_c_e_o_non_si_legge_e_none(rete: _Rete) -> None:
    url = f"{_STATO}/2026/07/06/1200/sites.geojson"
    rete.risposte[f"GET {url}"] = httpx.Response(403, text="AccessDenied")
    assert await client.get_radar_status(_T) is None
    assert len(rete.viste) == 1, "il 403 di S3 è «non c'è»: non si ritenta"
    rete.risposte[f"GET {url}"] = httpx.Response(200, json={"features": []})
    assert await client.get_radar_status(_T) is None
    rete.risposte[f"GET {url}"] = httpx.Response(503)
    assert await client.get_radar_status(_T) is None


async def test_la_serie_sri_non_riscarica_quello_che_ha(monkeypatch: pytest.MonkeyPatch) -> None:
    """#643: a regime la sveglia scarica solo l'SRI nuovo; i due prima sono in memoria,
    anche se l'ultimo avanza di 10 minuti invece che di 15."""
    import datetime as dt

    from limen.integrations.dpc import client as cli

    chiesti: list[object] = []
    t0 = dt.datetime(2026, 11, 19, 9, 0, tzinfo=dt.UTC)
    ultimo = {"t": t0}

    class _G:
        def __init__(self, t: dt.datetime) -> None:
            self.time = t

    async def _download(_p: str, cached: object = None, *, at: dt.datetime | None = None) -> object:
        chiesti.append(at or "ultimo")
        if at is None:
            if isinstance(cached, _G) and cached.time == ultimo["t"]:
                return cached
            return _G(ultimo["t"])
        return _G(at)

    monkeypatch.setattr(cli, "_download", _download)
    monkeypatch.setattr(cli, "_sri_cache", {})
    monkeypatch.setattr(cli, "_serie", None)
    passo = dt.timedelta(minutes=15)
    await cli.get_sri_series(passo, 3)
    assert len(chiesti) == 3
    for avanzo in (15, 10, 20):
        chiesti.clear()
        ultimo["t"] += dt.timedelta(minutes=avanzo)
        monkeypatch.setattr(cli, "_serie", None)
        serie = await cli.get_sri_series(passo, 3)
        assert [g.time for g in serie][-1] == ultimo["t"]
        assert len(chiesti) <= 3
    chiesti.clear()
    await cli.get_sri_series(passo, 3)  # stesso sweep: la serie appena letta
    assert chiesti == []
