"""Packaged GeoJSON seeds load and parse to valid Shapely geometries."""

from __future__ import annotations

import pytest
from shapely.geometry import MultiPolygon, Polygon

from limen.cli.seed import scegli
from limen.config.settings import InstallazioneSettings
from limen.data.seed.loader import load_all, load_basilicata, load_puglia


def test_load_puglia_returns_polygon_or_multipolygon() -> None:
    aoi = load_puglia()
    assert aoi.id == "it-puglia"
    assert isinstance(aoi.geom, MultiPolygon | Polygon)
    assert aoi.geom.is_valid
    assert aoi.geom.area > 0


def test_load_basilicata_returns_polygon_or_multipolygon() -> None:
    aoi = load_basilicata()
    assert aoi.id == "it-basilicata"
    assert isinstance(aoi.geom, MultiPolygon | Polygon)
    assert aoi.geom.is_valid


def test_load_all_returns_all_regions() -> None:
    aois = load_all()
    ids = {a.id for a in aois}
    # All 20 ISTAT regions, including the original pilot pair.
    assert len(aois) == 20
    assert {"it-puglia", "it-basilicata", "it-lombardia", "it-sicilia"} <= ids
    assert all(a.geom.is_valid and a.geom.area > 0 for a in aois)


def test_le_regioni_scelte_si_scrivono_come_si_vuole() -> None:
    """#407: `INSTALLAZIONE__REGIONI` la scrive una persona, in `installa.sh`."""
    assert InstallazioneSettings(regioni="").regioni_scelte is None
    assert InstallazioneSettings(regioni="tutte").regioni_scelte is None
    assert InstallazioneSettings(regioni="Puglia, it-basilicata").regioni_scelte == [
        "it-puglia",
        "it-basilicata",
    ]


def test_una_regione_sbagliata_ferma_il_seed() -> None:
    assert len(scegli(None)) == 20
    assert [a.id for a in scegli(["it-molise"])] == ["it-molise"]
    with pytest.raises(KeyError, match="it-atlantide"):
        scegli(["it-atlantide"])
