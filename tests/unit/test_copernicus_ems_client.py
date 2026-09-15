"""Client Copernicus EMS: il truth set dell'alluvione, senza rete (#116).

Il client parla con un servizio pubblico ma il valore da provare sta nel
parsing: quali attivazioni tenere, quale acquisizione ancora il preavviso,
come si leggono i vettori "observedEventA" da uno zip di zip. Qui la rete è
simulata con `respx`, i vettori sono shapefile veri scritti in una cartella
temporanea.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from shapely.geometry import MultiPolygon, Polygon

from limen.integrations._http import SharedHttpClient
from limen.integrations.copernicus_ems import client as ems

_DETAIL = {
    "results": [
        {
            "aois": [
                {
                    "number": 1,
                    "extent": "POLYGON((16 41, 17 41, 17 42, 16 42, 16 41))",
                    "products": [
                        {
                            "type": "del",
                            "monitoringNumber": 0,
                            "images": [
                                {"acquisitionTime": "2024-09-18T10:00:00Z"},
                                {"acquisitionTime": "2024-09-18T06:00:00Z"},
                                {"acquisitionTime": None},
                            ],
                        },
                        # Prodotto senza immagini: nessuna maschera, nessun istante.
                        {"type": "grad", "monitoringNumber": 1, "images": []},
                    ],
                },
                # WKT illeggibile: dato sporco, si salta e si prosegue.
                {"number": 2, "extent": "NON E' WKT", "products": []},
                # Nessuna estensione: niente da mascherare.
                {"number": 3, "extent": None, "products": []},
            ]
        },
        "non un dizionario",
    ]
}


@pytest.fixture(autouse=True)
async def _close_http():
    yield
    await SharedHttpClient.aclose()


def test_parse_dt_handles_z_naive_and_garbage() -> None:
    assert ems._parse_dt("2024-09-18T06:00:00Z") == datetime(2024, 9, 18, 6, tzinfo=UTC)
    assert ems._parse_dt("2024-09-18T06:00:00") == datetime(2024, 9, 18, 6, tzinfo=UTC)
    assert ems._parse_dt("ieri") is None
    assert ems._parse_dt(None) is None


@respx.mock
async def test_fetch_activations_paginates_filters_and_sorts() -> None:
    """Paese, categoria e data valida: le tre condizioni per entrare nel catalogo.

    `categories` è aperto perché la categoria EMS descrive la causa e non
    l'effetto: molte alluvioni italiane sono classificate "Storm".
    """
    page2 = f"{ems.ACTIVATIONS_URL}?page=2"
    respx.get(f"{ems.ACTIVATIONS_URL}?limit=500").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "code": "EMSR800",
                        "name": " Piemonte ",
                        "category": "Flood",
                        "eventTime": "2024-10-17T00:00:00Z",
                        "countries": ["Italy"],
                    },
                    {  # altro paese
                        "code": "EMSR801",
                        "category": "Flood",
                        "eventTime": "2024-10-01T00:00:00Z",
                        "countries": ["France"],
                    },
                    {  # data assente
                        "code": "EMSR802",
                        "category": "Flood",
                        "eventTime": None,
                        "countries": ["Italy"],
                    },
                ],
                "next": page2,
            },
        )
    )
    respx.get(page2).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "code": "EMSR700",
                        "category": "Storm",
                        "subCategory": "Heavy rain",
                        "eventTime": "2024-05-01T00:00:00Z",
                        "countries": ["Italy"],
                    },
                    {  # categoria non richiesta
                        "code": "EMSR701",
                        "category": "Wildfire",
                        "eventTime": "2024-06-01T00:00:00Z",
                        "countries": ["Italy"],
                    },
                ],
                "next": None,
            },
        )
    )

    out = await ems.fetch_activations(categories=("Flood", "Storm"))

    assert [a.code for a in out] == ["EMSR700", "EMSR800"]  # ordinate per data
    assert out[1].name == "Piemonte"  # spazi tolti
    assert out[0].sub_category == "Heavy rain"
    assert out[0].name == "EMSR700"  # senza nome si usa il codice


@respx.mock
async def test_observation_masks_skip_bad_extents_and_empty_products() -> None:
    respx.get(f"{ems.ACTIVATION_DETAIL_URL}?code=EMSR762").mock(
        return_value=httpx.Response(200, json=_DETAIL)
    )
    masks = await ems.fetch_observation_masks("EMSR762")

    assert len(masks) == 1
    mask = masks[0]
    assert mask.id == "EMSR762-aoi01-DEL0"
    assert mask.aoi_label == "AOI01"
    # L'istante più antico: è quando il satellite ha visto per la prima volta.
    assert mask.observed_time == datetime(2024, 9, 18, 6, tzinfo=UTC)


@respx.mock
async def test_acquisition_times_keep_the_earliest_per_product() -> None:
    respx.get(f"{ems.ACTIVATION_DETAIL_URL}?code=EMSR762").mock(
        return_value=httpx.Response(200, json=_DETAIL)
    )
    times = await ems._acquisition_times("EMSR762")
    assert times == {(1, "DEL", 0): datetime(2024, 9, 18, 6, tzinfo=UTC)}


def _zip_of_zips(members: dict[str, bytes]) -> bytes:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as zf:
        zf.writestr("EMSR762_AOI01_DEL_PRODUCT.zip", inner.getvalue())
        zf.writestr("leggimi.txt", b"non uno zip")
    return outer.getvalue()


def test_extract_vectors_keeps_only_observed_event_files(tmp_path: Path) -> None:
    archive = tmp_path / "products.zip"
    archive.write_bytes(
        _zip_of_zips(
            {
                "EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.shp": b"shp",
                "EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.dbf": b"dbf",
                "EMSR762_AOI01_DEL_PRODUCT_areaOfInterestA_v1.shp": b"altro",
            }
        )
    )
    found = ems._extract_vectors(archive, tmp_path / "out")
    assert found == 1
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == [
        "EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.dbf",
        "EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.shp",
    ]


async def test_ensure_vectors_uses_the_cache(tmp_path: Path) -> None:
    folder = tmp_path / "EMSR762"
    folder.mkdir()
    (folder / "x_observedEventA_v1.shp").write_bytes(b"")
    # Nessuna rete simulata: se provasse a scaricare, fallirebbe.
    assert await ems._ensure_vectors("EMSR762", cache_dir=tmp_path) == folder


@respx.mock
async def test_ensure_vectors_downloads_and_extracts(tmp_path: Path) -> None:
    respx.get(ems.PRODUCTS_URL.format(code="EMSR762")).mock(
        return_value=httpx.Response(
            200, content=_zip_of_zips({"EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.shp": b"x"})
        )
    )
    folder = await ems._ensure_vectors("EMSR762", cache_dir=tmp_path)
    assert folder is not None and any(folder.glob("*.shp"))
    # Il pacchetto da ~100 MB non resta su disco dopo l'estrazione.
    assert not (tmp_path / "EMSR762_products.zip").exists()


@respx.mock
async def test_ensure_vectors_degrades_on_a_private_package(tmp_path: Path) -> None:
    """EMSR664 risponde 403: un pacchetto non pubblico non ferma l'ingest."""
    respx.get(ems.PRODUCTS_URL.format(code="EMSR664")).mock(return_value=httpx.Response(403))
    assert await ems._ensure_vectors("EMSR664", cache_dir=tmp_path) is None
    assert not (tmp_path / "EMSR664_products.zip").exists()


@respx.mock
async def test_ensure_vectors_without_observed_events_is_none(tmp_path: Path) -> None:
    respx.get(ems.PRODUCTS_URL.format(code="EMSR900")).mock(
        return_value=httpx.Response(
            200, content=_zip_of_zips({"EMSR900_AOI01_DEL_PRODUCT_areaOfInterestA_v1.shp": b"x"})
        )
    )
    assert await ems._ensure_vectors("EMSR900", cache_dir=tmp_path) is None


def test_iter_polygons_explodes_multipolygons() -> None:
    a = Polygon([(0, 0), (1, 0), (1, 1)])
    b = Polygon([(2, 2), (3, 2), (3, 3)])
    assert list(ems._iter_polygons(MultiPolygon([a, b]))) == [a, b]
    assert list(ems._iter_polygons(a)) == [a]


@respx.mock
async def test_fetch_observed_floods_reads_real_shapefiles(tmp_path: Path) -> None:
    """Uno shapefile vero, con le righe che il filtro deve scartare.

    Una MultiPolygon diventa più righe, **ognuna con la propria area**: ripetere
    l'area del gruppo su ogni parte conterebbe lo stesso allagamento N volte.
    """
    import geopandas as gpd

    folder = tmp_path / "EMSR762"
    folder.mkdir()
    flooded = MultiPolygon(
        [
            Polygon([(16.0, 41.0), (16.01, 41.0), (16.01, 41.01), (16.0, 41.01)]),
            Polygon([(16.1, 41.1), (16.12, 41.1), (16.12, 41.12), (16.1, 41.12)]),
        ]
    )
    frame = gpd.GeoDataFrame(
        {
            "event_type": ["5-Flood", "5-Flood", "3-Fire"],
            "notation": ["Flooded area", "Burnt area", "Flooded area"],
            "obj_desc": ["Riverine flood", "x", "y"],
            "det_method": ["Radar", "", ""],
        },
        geometry=[flooded, flooded, flooded],
        crs="EPSG:4326",
    )
    frame.to_file(folder / "EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.shp")

    respx.get(f"{ems.ACTIVATION_DETAIL_URL}?code=EMSR762").mock(
        return_value=httpx.Response(200, json=_DETAIL)
    )
    activation = ems.Activation(
        code="EMSR762",
        name="Emilia",
        category="Flood",
        event_time=datetime(2024, 9, 17, tzinfo=UTC),
        countries=("Italy",),
    )

    out = await ems.fetch_observed_floods(activation, cache_dir=tmp_path)

    # Solo la prima riga passa entrambi i filtri, e diventa due parti.
    assert len(out) == 2
    assert {f.id for f in out} == {"EMSR762-aoi01-DEL0-0-0", "EMSR762-aoi01-DEL0-0-1"}
    assert all(f.observed_time == datetime(2024, 9, 18, 6, tzinfo=UTC) for f in out)
    assert out[0].detection_method == "Radar"
    # Aree diverse per le due parti: non l'area del gruppo ripetuta.
    assert out[0].area_km2 != out[1].area_km2
    assert all(f.area_km2 and f.area_km2 > 0 for f in out)


async def test_fetch_observed_floods_without_vectors_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _none(code: str, *, cache_dir: Path) -> None:
        return None

    monkeypatch.setattr(ems, "_ensure_vectors", _none)
    activation = ems.Activation(
        code="EMSR1",
        name="x",
        category="Flood",
        event_time=datetime(2024, 1, 1, tzinfo=UTC),
        countries=("Italy",),
    )
    assert await ems.fetch_observed_floods(activation, cache_dir=tmp_path) == []


def test_catalogue_provenance_declares_no_credentials() -> None:
    """Il truth set è aperto: se un giorno servissero credenziali, il report
    deve dirlo — ed è il dato che ha sbloccato la #64."""
    prov = ems.catalogue_provenance()
    assert prov["credentials"] == "none"
    assert prov["api"] == ems.ACTIVATIONS_URL
