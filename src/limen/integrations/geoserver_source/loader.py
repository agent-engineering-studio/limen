"""Load ISPRA static data from the GeoServer PostGIS into operational tables.

The GeoServer stack (mcp-geo-server) publishes the ISPRA open data as
per-region PostGIS tables. This loader reads the landslide inventory
families and the PAI hazard mosaic for one AOI and upserts them into the
operational ``iffi_landslides`` / ``pai_hazard`` tables, so the existing
``bootstrap-static`` per-cell aggregation runs unchanged.

Ogni riga porta in ``attributes`` la voce di ``config/dati.yaml`` da cui viene
(``dataset``) e la citazione che la licenza chiede (``citazione``, #666):
IFFI per regione, i mosaici con la loro versione. IFFI e i mosaici sono
CC BY-SA 4.0 (la PAI v. 5.0, se è quella scelta, CC BY 4.0: #670), quindi chi
esporta celle o report deve poterle riportare. Le
righe scritte prima le ricevono al sync dopo, con un ``UPDATE`` che tocca solo
quelle senza ``dataset``: non cambia la versione del dato, e il bootstrap non
ricalcola niente.

Una tabella attesa che non c'è (#665) non ferma il caricamento, ma non passa
più in silenzio: finisce nell'esito (``mancanti``), in ``dataset_versions``
(``geoserver`` / ``tabelle_mancanti:<aoi>``, letto dal riepilogo
``qualita-dati``) e in un log ``error``. Così una regione la cui tabella non è
arrivata si distingue da una regione senza frane censite: per un layer che
IdroGEO non ha, ``ispra-idrogeo`` scarica un file vuoto, che diventa una
tabella vuota, non una tabella assente.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Any

import asyncpg

from limen.config.catalogo_dati import carica_catalogo
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire, register_postgis
from limen.data.repos.dataset_versions_repo import content_hash, find, latest, record
from limen.data.repos.flood_repo import FloodHazard
from limen.data.repos.flood_repo import upsert_many as flood_upsert
from limen.data.repos.iffi_repo import IFFILandslide
from limen.data.repos.iffi_repo import upsert_many as iffi_upsert
from limen.data.repos.pai_repo import PAIHazard
from limen.data.repos.pai_repo import delete_prefisso as pai_delete_prefisso
from limen.data.repos.pai_repo import upsert_many as pai_upsert

log = get_logger(__name__)

# ISPRA hydraulic-hazard (idraulica) mosaic: published per severity as
# separate tables (HPH elevata / MPH media / LPH bassa). We discover them by
# name pattern so the loader works whether they were bootstrapped with the
# full sanitized basename or a short alias. Severity → shared AA/P1..P4 class.
# Le tre severità del mosaico idraulico, ciascuna con i nomi sotto cui la
# tabella può presentarsi. La parola italiana è quella del file sorgente; il
# codice a tre lettere è quello della Direttiva Alluvioni (High/Medium/Low
# Probability Hazard) e sopravvive dove la parola no.
#
# Serve entrambi perché il nome della tabella nasce dal nome dello shapefile e
# PostgreSQL tronca gli identificatori a 63 byte. Misurato:
# `HPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_elevata.shp` diventa
# `mosaicatura_ispra_2020_aree_pericolosita_idraulica_hph_4c7713bb` — la
# parola «elevata» è stata tagliata via, il codice `hph` no. Cercando solo la
# parola il sync tornava `flood: 0` con 85.000 poligoni già in tabella.
_IDRAULICA_SEVERITY: dict[str, tuple[str, ...]] = {
    "P3": ("elevata", "hph"),
    "P2": ("media", "mph"),
    "P1": ("bassa", "lph"),
}

# Landslide-inventory families published per region as
# ``<family>_<region>_opendata`` (polygons, lines, points).
_IFFI_FAMILIES = ("frane_poly", "frane_line", "frane_piff", "aree_poly", "dgpv_poly")

# IFFI has no Trentino-Alto Adige: it publishes the two autonomous provinces.
_IFFI_AREE = {"trentino_alto_adige": ("bolzano", "trento")}

# Chi pubblica l'IFFI di ogni area, per la citazione che la licenza chiede:
# «ISPRA - Regione X. Inventario dei Fenomeni Franosi in Italia - IFFI.
# idrogeo.isprambiente.it» (le 21 licenze per area, #406).
_ENTE_IFFI: dict[str, str] = {
    "piemonte": "Regione Piemonte",
    "valle_d_aosta": "Regione Valle d'Aosta",
    "lombardia": "Regione Lombardia",
    "bolzano": "Provincia Autonoma di Bolzano",
    "trento": "Provincia Autonoma di Trento",
    "veneto": "Regione Veneto",
    "friuli_venezia_giulia": "Regione Friuli Venezia Giulia",
    "liguria": "Regione Liguria",
    "emilia_romagna": "Regione Emilia-Romagna",
    "toscana": "Regione Toscana",
    "umbria": "Regione Umbria",
    "marche": "Regione Marche",
    "lazio": "Regione Lazio",
    "abruzzo": "Regione Abruzzo",
    "molise": "Regione Molise",
    "campania": "Regione Campania",
    "puglia": "Regione Puglia",
    "basilicata": "Regione Basilicata",
    "calabria": "Regione Calabria",
    "sicilia": "Regione Siciliana",
    "sardegna": "Regione Sardegna",
}


def citazione_iffi(area: str) -> str:
    """La citazione dell'IFFI di un'area (``puglia``, ``bolzano``), CC BY-SA 4.0."""
    ente = _ENTE_IFFI.get(area, "Regioni e Province Autonome")
    return (
        f"ISPRA \u2013 {ente}. Inventario dei Fenomeni Franosi in Italia - IFFI. "
        "idrogeo.isprambiente.it"
    )


def _citazione(voce: str) -> str:
    """L'attribuzione della voce del catalogo (``pai_frana``, ``idraulica``)."""
    return carica_catalogo().voce(voce).attribuzione or carica_catalogo().voce(voce).fonte


# National PAI landslide-hazard mosaic (single table, ~900k polygons), per
# valore di ``GEODATI__MOSAICO_PAI`` (#670): la tabella che ``carica-vettori``
# crea e il prefisso degli id in ``pai_hazard``. Il prefisso è diverso perché
# l'id è il ``fid``, e lo stesso numero nei due mosaici è un altro poligono in
# un'altra regione: con un prefisso solo, il sync di una regione
# sovrascriverebbe i poligoni di un'altra.
_PAI_MOSAICI: dict[str, tuple[str, str]] = {
    "pai_frane": ("mosaicatura_ispra_2020_2021_aree_pericolosita_frana_pai", "pai"),
    "pai_frane_2024": ("mosaicatura_ispra_2024_pericolosita_frana_pai", "pai2024"),
}
_PAI_ATTR = "per_fr_ita"

# Preferred stable id columns; fall back to a geometry hash when absent.
_ID_COL_PREFERENCE = ("id_frana", "fid", "ogc_fid", "gid", "objectid")

# PAI class token embedded in the free-text ``per_fr_ita`` label
# (e.g. "Aree di Attenzione AA", "Elevata P3").
_PAI_TOKEN_RE = re.compile(r"\b(AA|P[1-4])\b", re.IGNORECASE)


def _manca(schema: str, table: str, mancanti: list[str] | None = None) -> None:
    # Con le tabelle nel database di Limen (#426) una tabella assente è il
    # guasto normale — `carica-vettori` mai eseguito, o uno shapefile non
    # entrato — e lascerebbe la regione senza PAI o mosaico senza un errore.
    if mancanti is not None:
        mancanti.append(table)
    log.warning(
        "integration.degraded",
        source="geoserver_source",
        op="missing_table",
        table=f"{schema}.{table}",
        hint="limen carica-vettori",
    )


def _region_token(aoi_id: str) -> str:
    """Map an AOI id (e.g. ``it-puglia``) to the region table suffix."""
    token = aoi_id.strip().lower().replace("-", "_")
    for prefix in ("it_", "ita_"):
        if token.startswith(prefix):
            return token[len(prefix) :]
    return token


def _pai_class_token(value: str | None) -> str | None:
    if not value:
        return None
    match = _PAI_TOKEN_RE.search(value)
    return match.group(1).upper() if match else None


async def _table_columns(conn: asyncpg.Connection, schema: str, table: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        """,
        schema,
        table,
    )
    return {r["column_name"] for r in rows}


async def _aoi_bbox(aoi_id: str) -> tuple[float, float, float, float] | None:
    """Bounding box of the AOI's grid cells, for the PAI spatial filter."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_XMin(e) AS minx, ST_YMin(e) AS miny,
                   ST_XMax(e) AS maxx, ST_YMax(e) AS maxy
            FROM (SELECT ST_Extent(geom) AS e FROM grid_cells WHERE aoi_id = $1) s
            """,
            aoi_id,
        )
    if row is None or row["minx"] is None:
        return None
    return (float(row["minx"]), float(row["miny"]), float(row["maxx"]), float(row["maxy"]))


async def _load_iffi(
    conn: asyncpg.Connection, schema: str, region: str, mancanti: list[str] | None = None
) -> list[IFFILandslide]:
    items: list[IFFILandslide] = []
    for area in _IFFI_AREE.get(region, (region,)):
        for family in _IFFI_FAMILIES:
            table = f"{family}_{area}_opendata"
            cols = await _table_columns(conn, schema, table)
            if "geom" not in cols:
                _manca(schema, table, mancanti)
                continue
            id_col = next((c for c in _ID_COL_PREFERENCE if c in cols), None)
            id_expr = f'"{id_col}"::text' if id_col else 'md5(ST_AsEWKB("geom"))'
            move_col = "nome_tipo" if "nome_tipo" in cols else None
            move_expr = f'"{move_col}"::text' if move_col else "NULL::text"
            rows = await conn.fetch(
                f'SELECT {id_expr} AS rid, {move_expr} AS movement, "geom" AS geom '
                f'FROM "{schema}"."{table}"'
            )
            for r in rows:
                geom = r["geom"]
                if geom is None:
                    continue
                items.append(
                    IFFILandslide(
                        id=f"{table}:{r['rid']}",
                        movement_type=r["movement"],
                        state=None,
                        velocity_class=None,
                        # Gli shapefile open-data IFFI hanno solo tipo di
                        # movimento e geometria (#667). Le date (~28.000 frane
                        # su 721.000) sono solo nell'API di IdroGEO:
                        # `ispra_idrogeo.dated.dated_landslides`, non caricate.
                        occurrence_date=None,
                        geom=geom,
                        attributes={
                            "source": "geoserver",
                            "family": family,
                            "region": region,
                            "dataset": "iffi",
                            "citazione": citazione_iffi(area),
                        },
                    )
                )
    return items


async def _load_pai(
    conn: asyncpg.Connection,
    schema: str,
    bbox: tuple[float, float, float, float],
    mancanti: list[str] | None = None,
    *,
    mosaico: str,
) -> list[PAIHazard]:
    tabella, prefisso = _PAI_MOSAICI[mosaico]
    cols = await _table_columns(conn, schema, tabella)
    if "geom" not in cols or _PAI_ATTR not in cols:
        _manca(schema, tabella, mancanti)
        return []
    id_col = next((c for c in _ID_COL_PREFERENCE if c in cols), None)
    id_expr = f'"{id_col}"::text' if id_col else 'md5(ST_AsEWKB("geom"))'
    rows = await conn.fetch(
        f'SELECT {id_expr} AS rid, "{_PAI_ATTR}"::text AS cls, "geom" AS geom '
        f'FROM "{schema}"."{tabella}" '
        "WHERE ST_Intersects(geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))",
        bbox[0],
        bbox[1],
        bbox[2],
        bbox[3],
    )
    items: list[PAIHazard] = []
    citazione = _citazione("pai_frana")
    for r in rows:
        token = _pai_class_token(r["cls"])
        geom = r["geom"]
        if token is None or geom is None:
            continue
        items.append(
            PAIHazard(
                id=f"{prefisso}:{r['rid']}",
                hazard_class=token,
                authority=None,
                geom=geom,
                attributes={
                    "source": "geoserver",
                    "per_fr_ita": r["cls"],
                    "dataset": "pai_frana",
                    "citazione": citazione,
                },
            )
        )
    return items


async def _idraulica_tables(
    conn: asyncpg.Connection, schema: str, mancanti: list[str] | None = None
) -> dict[str, str]:
    """Discover the idraulica tables by severity → class token.

    Prova i nomi accettati per ciascuna severità e si ferma al primo che
    trova, saltando le tabelle già assegnate: due severità che puntano alla
    stessa tabella produrrebbero classi sovrapposte, e la peggiore vincerebbe
    per caso invece che per criterio.
    """
    found: dict[str, str] = {}
    for cls, keywords in _IDRAULICA_SEVERITY.items():
        for keyword in keywords:
            row = await conn.fetchrow(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = $1 AND tablename ILIKE $2
                ORDER BY tablename LIMIT 1
                """,
                schema,
                f"%idraulica%{keyword}%",
            )
            if row is None:
                continue
            table = str(row["tablename"])
            if table in found:
                continue
            found[table] = cls
            break
    if not found:
        _manca(schema, "mosaicatura_ispra_2020_aree_pericolosita_idraulica_*", mancanti)
    return found


async def _load_idraulica(
    conn: asyncpg.Connection,
    schema: str,
    bbox: tuple[float, float, float, float],
    mancanti: list[str] | None = None,
) -> list[FloodHazard]:
    items: list[FloodHazard] = []
    citazione = _citazione("idraulica")
    for table, cls in (await _idraulica_tables(conn, schema, mancanti)).items():
        cols = await _table_columns(conn, schema, table)
        if "geom" not in cols:
            continue
        id_col = next((c for c in _ID_COL_PREFERENCE if c in cols), None)
        id_expr = f'"{id_col}"::text' if id_col else 'md5(ST_AsEWKB("geom"))'
        rows = await conn.fetch(
            f'SELECT {id_expr} AS rid, "geom" AS geom '
            f'FROM "{schema}"."{table}" '
            "WHERE ST_Intersects(geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))",
            bbox[0],
            bbox[1],
            bbox[2],
            bbox[3],
        )
        for r in rows:
            geom = r["geom"]
            if geom is None:
                continue
            items.append(
                FloodHazard(
                    id=f"idr:{table}:{r['rid']}",
                    hazard_class=cls,
                    geom=geom,
                    attributes={
                        "source": "geoserver",
                        "table": table,
                        "dataset": "idraulica",
                        "citazione": citazione,
                    },
                )
            )
    return items


async def _se_cambiato(
    dataset: str,
    aoi_id: str,
    righe: list[bytes],
    scrivi: Callable[[], Awaitable[int]],
    *,
    mosaico: str | None = None,
) -> int:
    """Scrive solo se le righe dell'AOI non sono quelle dell'ultimo sync.

    Il sync gira due volte per regione a ogni `load_static_data.sh` (il passo
    «Sorgenti» e poi il bootstrap) e riscriveva ogni volta tutto: 14.685
    poligoni idraulici della Puglia sono nove minuti di ST_Subdivide (#407).
    Le righe si **ordinano** prima dell'hash: la query non ha ORDER BY, e la
    versione dell'alluvione, che già c'era, cambiava a ogni giro su Puglia.

    ``mosaico`` (solo il PAI, #670): se l'ultimo sync dell'AOI ne ha letto un
    altro si scrive comunque, e il cambio si registra con una versione sua.
    ``dataset_versions`` ricorda una versione per sempre, e così il bootstrap
    statico: tornando a un mosaico già usato, sia qui sia il passo ``pai``
    risponderebbero «invariato» con in tabella i poligoni dell'altro.
    """
    if not righe:
        return 0
    nome = f"{dataset}:{aoi_id}"
    versione = content_hash(sorted(righe))
    cambio = mosaico is not None and await _mosaico_dell_ultimo_sync(nome) not in (None, mosaico)
    if not cambio and await find("geoserver", nome, versione):
        log.info("geoserver_source.unchanged", aoi_id=aoi_id, dataset=dataset, items=len(righe))
        return 0
    n = await scrivi()
    metadata: dict[str, Any] = {"items": len(righe)}
    if mosaico is not None:
        metadata["mosaico"] = mosaico
    await record(source="geoserver", dataset=nome, version=versione, metadata=metadata)
    if cambio:
        await record(
            source="geoserver",
            dataset=nome,
            version=content_hash([versione, datetime.now(UTC).isoformat()]),
            metadata=metadata,
        )
    return n


async def _mosaico_dell_ultimo_sync(nome: str) -> str | None:
    """Il mosaico PAI dell'ultima versione scritta, ``None`` se non c'è mai stato un sync.

    Una riga senza ``mosaico`` è di prima di #670, quando c'era solo la v. 4.0.
    """
    ultima = await latest("geoserver", nome)
    if ultima is None:
        return None
    return str(ultima.metadata.get("mosaico", "pai_frane"))


async def _completa_attributi(tabella: str, items: Iterable[Any]) -> int:
    """Dataset e citazione alle righe scritte prima di #666; quante ne tocca.

    Solo le righe senza ``dataset``: dal secondo giro non tocca niente. Non
    passa da ``_se_cambiato``, perché non cambia il dato né la sua versione.
    """
    gruppi: dict[str, list[str]] = defaultdict(list)
    extra: dict[str, dict[str, Any]] = {}
    for item in items:
        chiave = json.dumps(
            {"dataset": item.attributes["dataset"], "citazione": item.attributes["citazione"]},
            ensure_ascii=False,
            sort_keys=True,
        )
        gruppi[chiave].append(item.id)
        extra[chiave] = json.loads(chiave)
    toccate = 0
    async with acquire() as conn:
        for chiave, ids in gruppi.items():
            esito = await conn.execute(
                f"UPDATE {tabella} SET attributes = attributes || $2::jsonb "
                "WHERE id = ANY($1::text[]) AND NOT (attributes ? 'dataset')",
                ids,
                json.dumps(extra[chiave], ensure_ascii=False),
            )
            toccate += int(str(esito).rsplit(" ", 1)[-1] or 0)
    return toccate


#: Il dataset di ``dataset_versions`` con le tabelle attese e non trovate.
DATASET_MANCANTI = "tabelle_mancanti"


async def _registra_mancanti(aoi_id: str, mancanti: list[str]) -> None:
    """Lo stato delle tabelle mancanti dell'AOI in ``dataset_versions`` (#665).

    Una riga per ogni stato nuovo, anche quello vuoto: così il riepilogo
    ``qualita-dati`` legge l'ultimo e una tabella tornata smette di comparire.
    """
    tabelle = sorted(set(mancanti))
    versione = content_hash(tabelle) if tabelle else "nessuna"
    dataset = f"{DATASET_MANCANTI}:{aoi_id}"
    if await find("geoserver", dataset, versione):
        return
    await record(
        source="geoserver", dataset=dataset, version=versione, metadata={"tabelle": tabelle}
    )


async def sync_geoserver_source_for_aoi(aoi_id: str) -> dict[str, int]:
    """Sync IFFI + PAI for ``aoi_id`` from GeoServer PostGIS.

    Returns per-dataset row counts, plus ``mancanti``: how many expected
    tables were not found (#665; their names are in ``dataset_versions``).
    No-op (all zeros) when the source DSN is unset; degrades to zeros + an
    ``integration.degraded`` log when the GeoServer PostGIS is unreachable
    (read side never raises).
    """
    settings = get_settings()
    dsn, schema = settings.geoserver_source.sorgente(settings.db)
    mosaico = settings.geodati.mosaico_pai

    region = _region_token(aoi_id)
    bbox = await _aoi_bbox(aoi_id)

    try:
        conn = await asyncpg.connect(dsn)
    except (OSError, asyncpg.PostgresError) as exc:
        log.warning("integration.degraded", source="geoserver_source", op="connect", error=str(exc))
        return {"iffi": 0, "pai": 0, "flood": 0, "mancanti": 0}

    mancanti: list[str] = []
    try:
        await register_postgis(conn)
        iffi_items = await _load_iffi(conn, schema, region, mancanti)
        pai_items = await _load_pai(conn, schema, bbox, mancanti, mosaico=mosaico) if bbox else []
        flood_items = await _load_idraulica(conn, schema, bbox, mancanti) if bbox else []
    except (OSError, asyncpg.PostgresError) as exc:
        log.warning("integration.degraded", source="geoserver_source", op="read", error=str(exc))
        return {"iffi": 0, "pai": 0, "flood": 0, "mancanti": 0}
    finally:
        await conn.close()

    if mancanti:
        log.error(
            "geoserver_source.tabelle_mancanti",
            aoi_id=aoi_id,
            tabelle=mancanti,
            hint="limen geodati-sync, poi limen carica-vettori",
        )
    await _registra_mancanti(aoi_id, mancanti)

    iffi_n = await _se_cambiato(
        "iffi",
        aoi_id,
        [f"{i.id}|{i.movement_type}".encode() + i.geom.wkb for i in iffi_items],
        lambda: iffi_upsert(iffi_items),
    )

    async def scrivi_pai() -> int:
        n = await pai_upsert(pai_items)
        # Dopo un cambio di mosaico i poligoni dell'altro resterebbero accanto
        # ai nuovi, e la cella prenderebbe la classe più alta fra i due. Dopo
        # l'upsert: se fallisce, il giro dopo trova ancora il cambio da fare.
        if bbox:
            for altro, (_, prefisso) in _PAI_MOSAICI.items():
                if altro != mosaico:
                    await pai_delete_prefisso(f"{prefisso}:", bbox)
        return n

    pai_n = await _se_cambiato(
        "pai",
        aoi_id,
        [f"{i.id}|{i.hazard_class}".encode() + i.geom.wkb for i in pai_items],
        scrivi_pai,
        mosaico=mosaico,
    )
    # Flood upsert is the slow step (ST_Subdivide over Po-plain mega-polygons,
    # minutes per region).
    flood_n = await _se_cambiato(
        "flood",
        aoi_id,
        [f"{i.id}|{i.hazard_class}".encode() + i.geom.wkb for i in flood_items],
        lambda: flood_upsert(flood_items),
    )
    # Le righe di prima di #666, che `_se_cambiato` ha trovato invariate.
    completate = 0
    for tabella, items in (
        ("iffi_landslides", iffi_items),
        ("pai_hazard", pai_items),
        ("flood_hazard", flood_items),
    ):
        if items:
            completate += await _completa_attributi(tabella, items)
    if completate:
        log.info("geoserver_source.citazioni_aggiunte", aoi_id=aoi_id, righe=completate)
    log.info(
        "geoserver_source.synced",
        aoi_id=aoi_id,
        region=region,
        iffi=iffi_n,
        pai=pai_n,
        flood=flood_n,
        mancanti=len(mancanti),
    )
    return {"iffi": iffi_n, "pai": pai_n, "flood": flood_n, "mancanti": len(mancanti)}
