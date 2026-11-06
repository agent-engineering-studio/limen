"""Unit tests for the GeoServer-source pure helpers + reweighted S."""

from __future__ import annotations

from typing import cast

import asyncpg
import pytest
from shapely.geometry import Point

from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.integrations.geoserver_source import loader
from limen.integrations.geoserver_source.loader import _pai_class_token, _region_token


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Aree di Attenzione AA", "AA"),
        ("Moderata P1", "P1"),
        ("Media P2", "P2"),
        ("Elevata P3", "P3"),
        ("Molto elevata P4", "P4"),
        ("elevata p3", "P3"),
        ("qualcosa senza classe", None),
        ("", None),
        (None, None),
    ],
)
def test_pai_class_token(value: str | None, expected: str | None) -> None:
    assert _pai_class_token(value) == expected


@pytest.mark.parametrize(
    ("aoi_id", "expected"),
    [
        ("it-puglia", "puglia"),
        ("it-basilicata", "basilicata"),
        ("puglia", "puglia"),
        ("IT-Valle-d-Aosta", "valle_d_aosta"),
    ],
)
def test_region_token(aoi_id: str, expected: str) -> None:
    assert _region_token(aoi_id) == expected


def test_static_weights_reweighted_and_gate_disabled() -> None:
    """Susceptibility is dropped from S; the S↔ISPRA gate is disabled."""
    t = load_regional_thresholds()
    w = t.static.weights
    assert w.susc_ispra == 0.0
    # Weight redistributed onto the GeoServer-sourced inputs + slope.
    assert w.iffi_density == pytest.approx(0.375)
    assert w.slope == pytest.approx(0.30)
    assert w.pai == pytest.approx(0.225)
    assert t.calibration.s_vs_ispra_correlation_min is None


def test_senza_dsn_i_vettori_si_leggono_dal_database_di_limen() -> None:
    """#426: GeoServer non serve più ai numeri. Chi aveva già un DSN verso il
    PostGIS di mcp-geo-server continua a leggere da `public`."""
    from limen.config.settings import DBSettings, GeoServerSourceSettings

    db = DBSettings(connection_string="postgresql://limen:limen@postgres:5432/limen")
    assert GeoServerSourceSettings().sorgente(db) == (db.connection_string, "sorgenti")
    assert GeoServerSourceSettings(db_dsn="", schema_name="").sorgente(db) == (
        db.connection_string,
        "sorgenti",
    )
    esterno = "postgresql://gis:gis@geoserver-postgis:5432/gis"
    assert GeoServerSourceSettings(db_dsn=esterno).sorgente(db) == (esterno, "public")


async def test_trentino_alto_adige_legge_le_due_province(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IFFI non pubblica la regione: senza le province le sue celle restano senza frane."""
    lette: list[str] = []

    async def colonne(_conn: object, _schema: str, tabella: str) -> set[str]:
        lette.append(tabella)
        return {"geom", "id_frana"}

    class Conn:
        async def fetch(self, _sql: str) -> list[dict[str, object]]:
            return [{"rid": "1", "movement": None, "geom": Point(11.0, 46.5)}]

    monkeypatch.setattr(loader, "_table_columns", colonne)
    frane = await loader._load_iffi(cast(asyncpg.Connection, Conn()), "s", "trentino_alto_adige")

    famiglie = len(loader._IFFI_FAMILIES)
    assert len(lette) == len(frane) == 2 * famiglie
    assert sum("_bolzano_" in t for t in lette) == famiglie
    assert sum("_trento_" in t for t in lette) == famiglie
    assert len({f.id for f in frane}) == len(frane)
