"""Client Copernicus EMS: il truth set dell'alluvione, senza rete (#116).

Il parsing sta nel pacchetto ``copernicus-ems``, che ha i suoi test; qui si
prova quello che resta di Limen: quali attivazioni si tengono, come una
feature diventa una riga di `flood_events` (id stabile, area per parte, ora
del satellite), la cache dei layer e il degrado di un layer illeggibile. La
rete è simulata con `respx`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import MultiPolygon, Polygon, mapping

from limen.integrations._http import SharedHttpClient
from limen.integrations.copernicus_ems import client as ems

_LAYER_URL = (
    "https://s3.example/EMSR762/AOI01/DEL_PRODUCT/EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.json"
)
_LAYER_NAME = "EMSR762/AOI01/DEL_PRODUCT/EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1_VT"

_DETAIL: dict[str, Any] = {
    "results": [
        {
            "code": "EMSR762",
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
                            "layers": [{"name": _LAYER_NAME, "format": "vt", "json": _LAYER_URL}],
                        },
                        # Prodotto senza immagini: nessuna maschera, nessun istante.
                        {"type": "gra", "monitoringNumber": 1, "images": [], "layers": []},
                        # Consegnato ma di sole ortofoto: né maschera né rimozione.
                        {
                            "type": "gra",
                            "monitoringNumber": 2,
                            "images": [{"acquisitionTime": "2024-09-19T10:00:00Z"}],
                            "layers": [{"name": "EMSR762_ORTHO.tif", "format": "cog"}],
                        },
                    ],
                },
                # WKT illeggibile: dato sporco, si salta e si prosegue.
                {
                    "number": 2,
                    "extent": "NON E' WKT",
                    "products": [
                        {"type": "del", "images": [{"acquisitionTime": "2024-09-18T06:00:00"}]}
                    ],
                },
                # Nessuna estensione: niente da mascherare.
                {"number": 3, "extent": None, "products": []},
            ],
        }
    ]
}

_FLOODED = MultiPolygon(
    [
        Polygon([(16.0, 41.0), (16.01, 41.0), (16.01, 41.01), (16.0, 41.01)]),
        Polygon([(16.1, 41.1), (16.12, 41.1), (16.12, 41.12), (16.1, 41.12)]),
    ]
)


def _feature(event_type: str, notation: str, **extra: str) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {"event_type": event_type, "notation": notation, **extra},
        "geometry": mapping(_FLOODED),
    }


# La prima feature non passa il filtro: la posizione nell'id resta quella nel
# layer intero, come nello shapefile del pacchetto, o l'upsert duplicherebbe.
_LAYER = {
    "type": "FeatureCollection",
    "features": [
        _feature("3-Fire", "Flooded area"),
        _feature("5-Flood", "Flooded area", obj_desc="Riverine flood", det_method="Radar"),
        _feature("5-Flood", "Burnt area"),
    ],
}

_ACTIVATION = ems.Activation(
    code="EMSR762",
    name="Emilia",
    category="Flood",
    event_time=datetime(2024, 9, 17, tzinfo=UTC),
    countries=("Italy",),
)


@pytest.fixture(autouse=True)
async def _close_http():
    yield
    await SharedHttpClient.aclose()


def _detail() -> None:
    respx.get(url__startswith=f"{ems.DETAIL_URL}?code=EMSR762").mock(
        return_value=httpx.Response(200, json=_DETAIL)
    )


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
async def test_observed_floods_come_from_the_geojson_layer(tmp_path: Path) -> None:
    """Una MultiPolygon diventa più righe, **ognuna con la propria area**:
    ripetere l'area del gruppo su ogni parte conterebbe lo stesso allagamento
    N volte."""
    _detail()
    layer = respx.get(_LAYER_URL).mock(return_value=httpx.Response(200, json=_LAYER))

    truth = await ems.fetch_activation_truth(_ACTIVATION, cache_dir=tmp_path)
    out = truth.floods

    assert {f.id for f in out} == {"EMSR762-aoi01-DEL0-1-0", "EMSR762-aoi01-DEL0-1-1"}
    assert all(f.observed_time == datetime(2024, 9, 18, 6, tzinfo=UTC) for f in out)
    assert out[0].detection_method == "Radar"
    assert out[0].event_type == "Riverine flood"
    assert out[0].area_km2 != out[1].area_km2
    assert all(f.area_km2 > 0 for f in out)
    assert out[0].attributes is not None
    assert out[0].attributes["product"] == "EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.json"

    # Il secondo giro legge la cache: il layer non si richiede.
    again = await ems.fetch_activation_truth(_ACTIVATION, cache_dir=tmp_path)
    assert [f.id for f in again.floods] == [f.id for f in out]
    assert layer.call_count == 1
    cached = tmp_path / "EMSR762" / _LAYER_URL.rsplit("/", 1)[-1]
    assert json.loads(cached.read_text()) == json.loads(json.dumps(_LAYER))


@respx.mock
async def test_a_mask_only_where_the_observed_layer_was_read(tmp_path: Path) -> None:
    """La maschera dice «qui si è guardato»: senza il layer letto direbbe
    asciutto un posto di cui non si sa niente.

    Nel dettaglio: AOI01 DEL ha il layer (maschera, con l'istante più antico);
    AOI01 GRA non ha immagini né layer; AOI02 ha immagini ma né layer né un WKT
    leggibile. Resta una maschera sola.
    """
    _detail()
    respx.get(_LAYER_URL).mock(return_value=httpx.Response(200, json=_LAYER))
    truth = await ems.fetch_activation_truth(_ACTIVATION, cache_dir=tmp_path)
    (mask,) = truth.masks
    assert mask.id == "EMSR762-aoi01-DEL0"
    # Senza alcun layer nel dettaglio: mai consegnati, da togliere se un
    # ingest precedente li aveva scritti. Il GRA2 di sole ortofoto è stato
    # consegnato: non si scrive e non si toglie.
    assert truth.absent_masks == ["EMSR762-aoi01-GRA1", "EMSR762-aoi02-DEL0"]
    assert "EMSR762-aoi01-GRA2" not in {m.id for m in truth.masks}
    # I soli prodotti di cui un poligono scomparso è davvero stato tolto.
    assert truth.prodotti_letti == [
        "EMSR762-aoi01-DEL0",
        "EMSR762-aoi01-GRA1",
        "EMSR762-aoi02-DEL0",
    ]
    assert mask.aoi_label == "AOI01"
    assert mask.observed_time == datetime(2024, 9, 18, 6, tzinfo=UTC)


@respx.mock
async def test_an_unreadable_layer_gives_neither_polygons_nor_mask(tmp_path: Path) -> None:
    _detail()
    respx.get(_LAYER_URL).mock(return_value=httpx.Response(403))
    truth = await ems.fetch_activation_truth(_ACTIVATION, cache_dir=tmp_path)
    assert truth.floods == [] and truth.masks == []
    # Il layer c'è ma non è arrivato: errore transitorio, la maschera di
    # prima (con i suoi poligoni) resta.
    assert "EMSR762-aoi01-DEL0" not in truth.absent_masks
    assert "EMSR762-aoi01-DEL0" not in truth.prodotti_letti
    assert not (tmp_path / "EMSR762").exists()


@respx.mock
async def test_a_corrupt_cache_is_downloaded_again(tmp_path: Path) -> None:
    _detail()
    layer = respx.get(_LAYER_URL).mock(return_value=httpx.Response(200, json=_LAYER))
    cached = tmp_path / "EMSR762" / _LAYER_URL.rsplit("/", 1)[-1]
    cached.parent.mkdir()
    cached.write_text("{troncato")
    truth = await ems.fetch_activation_truth(_ACTIVATION, cache_dir=tmp_path)
    assert len(truth.floods) == 2
    assert layer.call_count == 1


@respx.mock
async def test_an_unreachable_detail_is_empty(tmp_path: Path) -> None:
    respx.get(url__startswith=f"{ems.DETAIL_URL}?code=EMSR762").mock(
        return_value=httpx.Response(200, text="<html>manutenzione</html>")
    )
    truth = await ems.fetch_activation_truth(_ACTIVATION, cache_dir=tmp_path)
    assert truth.floods == [] and truth.masks == [] and truth.absent_masks == []


def test_catalogue_provenance_declares_no_credentials() -> None:
    """Il truth set è aperto: se un giorno servissero credenziali, il report
    deve dirlo — ed è il dato che ha sbloccato la #64."""
    prov = ems.catalogue_provenance()
    assert prov["credentials"] == "none"
    assert prov["api"] == ems.ACTIVATIONS_URL
