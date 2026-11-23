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
    # La citazione è quella dell'ente che pubblica l'area, non della regione (#666).
    bolzano = next(f for f in frane if "_bolzano_" in f.id)
    assert bolzano.attributes is not None
    assert bolzano.attributes["dataset"] == "iffi"
    assert "Provincia Autonoma di Bolzano" in bolzano.attributes["citazione"]


async def test_lo_stesso_insieme_in_altro_ordine_non_si_riscrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La query non ha ORDER BY: senza ordinare, la Puglia si riscriveva ogni giro (#407)."""
    versioni: set[tuple[str, str]] = set()
    scritture: list[int] = []

    async def trova(_fonte: str, dataset: str, versione: str) -> object | None:
        return object() if (dataset, versione) in versioni else None

    async def registra(*, source: str, dataset: str, version: str, metadata: object) -> None:
        versioni.add((dataset, version))

    async def scrivi() -> int:
        scritture.append(1)
        return 2

    monkeypatch.setattr(loader, "find", trova)
    monkeypatch.setattr(loader, "record", registra)

    assert await loader._se_cambiato("flood", "it-puglia", [b"a", b"b"], scrivi) == 2
    assert await loader._se_cambiato("flood", "it-puglia", [b"b", b"a"], scrivi) == 0
    assert await loader._se_cambiato("flood", "it-molise", [b"b", b"a"], scrivi) == 2
    assert await loader._se_cambiato("flood", "it-puglia", [b"a", b"c"], scrivi) == 2
    assert len(scritture) == 3


def test_la_citazione_iffi_nomina_l_ente_dell_area() -> None:
    assert loader.citazione_iffi("puglia") == (
        "ISPRA \u2013 Regione Puglia. Inventario dei Fenomeni Franosi in Italia - IFFI. "
        "idrogeo.isprambiente.it"
    )
    assert "Regione Siciliana" in loader.citazione_iffi("sicilia")
    # Ogni area che il loader legge ha il suo ente.
    from limen.integrations.idrogeo.geodati import AREE

    for area in AREE:
        assert area.replace("-", "_") in loader._ENTE_IFFI, area


async def test_pai_e_idraulica_portano_la_voce_e_la_citazione_del_catalogo() -> None:
    class Conn:
        async def fetch(self, _sql: str, *_a: object) -> list[dict[str, object]]:
            return [{"rid": "7", "cls": "Elevata P3", "geom": Point(16, 41)}]

    async def colonne(_conn: object, _schema: str, _tabella: str) -> set[str]:
        return {"geom", "per_fr_ita", "objectid"}

    mp = pytest.MonkeyPatch()
    mp.setattr(loader, "_table_columns", colonne)
    try:
        pai = await loader._load_pai(cast(asyncpg.Connection, Conn()), "s", (0, 0, 1, 1))
    finally:
        mp.undo()
    assert pai[0].attributes is not None
    assert pai[0].attributes["dataset"] == "pai_frana"
    assert "(v. 4.0" in pai[0].attributes["citazione"]


async def test_le_righe_di_prima_ricevono_la_citazione_una_volta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un UPDATE per citazione, solo sulle righe senza `dataset`."""
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from limen.data.repos.iffi_repo import IFFILandslide

    eseguite: list[tuple[str, list[str], str]] = []

    class Conn:
        async def execute(self, sql: str, ids: list[str], extra: str) -> str:
            eseguite.append((sql, ids, extra))
            return f"UPDATE {len(ids)}"

    @asynccontextmanager
    async def acquisisci() -> AsyncIterator[Conn]:
        yield Conn()

    monkeypatch.setattr(loader, "acquire", acquisisci)

    def frana(id_: str, area: str) -> IFFILandslide:
        return IFFILandslide(
            id=id_,
            movement_type=None,
            state=None,
            velocity_class=None,
            occurrence_date=None,
            geom=Point(11, 46),
            attributes={"dataset": "iffi", "citazione": loader.citazione_iffi(area)},
        )

    n = await loader._completa_attributi(
        "iffi_landslides", [frana("a", "bolzano"), frana("b", "trento"), frana("c", "bolzano")]
    )
    assert n == 3
    assert len(eseguite) == 2
    assert all("NOT (attributes ? 'dataset')" in sql for sql, _, _ in eseguite)
    assert sorted(ids for _, ids, _ in eseguite) == [["a", "c"], ["b"]]


async def test_una_tabella_mancante_finisce_nell_esito_e_nello_stato(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#665: la tabella che manca si conta e si registra; quella vuota no."""

    async def colonne(_conn: object, _schema: str, tabella: str) -> set[str]:
        # frane_line: tabella assente. frane_piff: presente ma vuota (IdroGEO
        # non ha il layer e ispra-idrogeo scarica un file vuoto).
        return set() if tabella.startswith("frane_line_") else {"geom", "id_frana", "per_fr_ita"}

    class Conn:
        async def fetch(self, sql: str, *_a: object) -> list[dict[str, object]]:
            if "frane_piff_" in sql:
                return []
            return [{"rid": "1", "movement": None, "cls": "Elevata P3", "geom": Point(16, 41)}]

        async def fetchrow(self, *_a: object) -> dict[str, object] | None:
            return None  # nessuna tabella idraulica

        async def close(self) -> None:
            return None

    registrati: list[tuple[str, str, object]] = []

    async def trova(*_a: object) -> None:
        return None

    async def registra(*, source: str, dataset: str, version: str, metadata: object) -> None:
        registrati.append((dataset, version, metadata))

    async def connetti(_dsn: str) -> Conn:
        return Conn()

    async def niente(*_a: object, **_k: object) -> None:
        return None

    async def riquadro(_aoi: str) -> tuple[float, float, float, float]:
        return (15.0, 40.0, 17.0, 42.0)

    async def scrivi(items: list[object]) -> int:
        return len(items)

    monkeypatch.setattr(loader, "_table_columns", colonne)
    monkeypatch.setattr(loader.asyncpg, "connect", connetti)
    monkeypatch.setattr(loader, "register_postgis", niente)
    monkeypatch.setattr(loader, "_aoi_bbox", riquadro)
    monkeypatch.setattr(loader, "find", trova)
    monkeypatch.setattr(loader, "record", registra)
    monkeypatch.setattr(loader, "iffi_upsert", scrivi)
    monkeypatch.setattr(loader, "pai_upsert", scrivi)

    async def completa(_tabella: str, _items: object) -> int:  # #666, sul DB
        return 0

    monkeypatch.setattr(loader, "_completa_attributi", completa)

    esito = await loader.sync_geoserver_source_for_aoi("it-puglia")

    assert esito["mancanti"] == 2
    assert esito["iffi"] == 3  # poly, aree, dgpv: la piff vuota non manca
    stato = [r for r in registrati if r[0] == "tabelle_mancanti:it-puglia"]
    assert len(stato) == 1
    assert stato[0][2] == {
        "tabelle": [
            "frane_line_puglia_opendata",
            "mosaicatura_ispra_2020_aree_pericolosita_idraulica_*",
        ]
    }


async def test_lo_stato_senza_tabelle_mancanti_si_registra_una_volta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uno stato vuoto chiude quello vecchio, ma non si riscrive a ogni giro."""
    versioni: set[tuple[str, str]] = set()

    async def trova(_fonte: str, dataset: str, versione: str) -> object | None:
        return object() if (dataset, versione) in versioni else None

    async def registra(*, source: str, dataset: str, version: str, metadata: object) -> None:
        versioni.add((dataset, version))

    monkeypatch.setattr(loader, "find", trova)
    monkeypatch.setattr(loader, "record", registra)
    await loader._registra_mancanti("it-puglia", [])
    await loader._registra_mancanti("it-puglia", [])
    assert versioni == {("tabelle_mancanti:it-puglia", "nessuna")}


@pytest.mark.parametrize(("rigoroso", "uscita"), [("", 0), ("1", 1)])
async def test_geoserver_sync_rigoroso_esce_con_1_se_manca_una_tabella(
    monkeypatch: pytest.MonkeyPatch, rigoroso: str, uscita: int
) -> None:
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from limen.cli import geoserver_sync

    @asynccontextmanager
    async def pool() -> AsyncIterator[None]:
        yield

    async def niente() -> None:
        return None

    async def aoi() -> list[str]:
        return ["it-molise", "it-puglia"]

    async def sync(aoi_id: str) -> dict[str, int]:
        return {"iffi": 0, "pai": 0, "flood": 0, "mancanti": int(aoi_id == "it-molise")}

    monkeypatch.setattr(geoserver_sync, "lifespan_pool", pool)
    monkeypatch.setattr(geoserver_sync, "run_migrations", niente)
    monkeypatch.setattr(geoserver_sync, "list_aoi_ids", aoi)
    monkeypatch.setattr(geoserver_sync, "sync_geoserver_source_for_aoi", sync)
    monkeypatch.setenv(geoserver_sync.RIGOROSO_ENV, rigoroso)
    assert await geoserver_sync.run() == uscita
