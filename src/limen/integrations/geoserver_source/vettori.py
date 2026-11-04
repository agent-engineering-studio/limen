"""I vettori ISPRA e ISTAT nel database di Limen, senza GeoServer (#426).

Ai calcoli di Limen GeoServer serviva per un passo solo: portare gli
shapefile della sua cartella (IFFI regione per regione, i mosaici PAI e
idraulico, i confini dei comuni) in tabelle PostGIS che ``loader.py``,
``seed-comuni`` e il lookup dei comuni leggono per nome. Qui lo stesso passo
lo fa Limen, nello schema ``sorgenti`` del proprio database (migrazione 087),
con le stesse convenzioni di mcp-geo-server — così quei lettori non cambiano:

* nome della tabella: la cartella, o cartella + file se la cartella ne ha più
  d'uno, accorciato a 63 caratteri come fa il driver PostgreSQL di GDAL;
* colonna ``geom`` multi-parte in EPSG:4326, chiave ``fid`` progressiva da 1
  nell'ordine del file (è l'id delle aree PAI e idrauliche);
* attributi come testo, con i nomi in minuscolo: il loader li legge ``::text``.

Si legge a blocchi per FID (accesso diretto dall'indice ``.shx``): il mosaico
PAI sono 928.000 poligoni e 1,9 GB, e non deve mai stare tutto in memoria. La
tabella nuova si costruisce accanto alla vecchia e si scambia alla fine, in
una transazione: chi legge vede o la vecchia o la nuova, mai una a metà.
Rieseguire non scrive niente se lo shapefile non è cambiato (mtime e
dimensione nel commento della tabella).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

SCHEMA = "sorgenti"
#: Forme per blocco. Misurato: 5.000 poligoni del mosaico idraulico sono
#: 150 MB di WKB; a 1.000 il picco resta sulle decine di MB anche lì.
LOTTO = 1000
_PG_IDENTIFICATORE_MAX = 63
#: Il pool ha 30 s per comando: l'indice spaziale su 928.000 poligoni PAI
#: (e un blocco di poligoni idraulici da 150 MB) ne chiedono molti di più.
_TIMEOUT_S = 3600.0

#: Le cartelle di cui Limen legge le tabelle; il resto della cartella di
#: GeoServer (CORINE, geolitologia, DTM) entra nei fattori da file.
_CARTELLE = (
    "frane_poly_*_opendata",
    "frane_line_*_opendata",
    "frane_piff_*_opendata",
    "aree_poly_*_opendata",
    "dgpv_poly_*_opendata",
    "Mosaicatura_ISPRA_2020_2021_aree_pericolosita_frana_PAI",
    "Mosaicatura_ISPRA_2020_aree_pericolosita_idraulica",
    "Limiti01012023_g/Com01012023_g",
)


def _identificatore(nome: str, *, accorcia: bool = True) -> str:
    pulito = re.sub(r"[^a-z0-9_]+", "_", nome.lower()).strip("_")
    if pulito and pulito[0].isdigit():
        pulito = f"_{pulito}"
    if accorcia and len(pulito) > _PG_IDENTIFICATORE_MAX:
        # Come GDAL con `-nln`: primi 54 caratteri, `_`, 8 esadecimali dell'MD5.
        impronta = hashlib.md5(pulito.encode(), usedforsecurity=False).hexdigest()[:8]
        pulito = f"{pulito[: _PG_IDENTIFICATORE_MAX - 9]}_{impronta}"
    return pulito or "layer"


def nome_tabella(shp: Path) -> str:
    """Il nome che mcp-geo-server dà alla tabella di ``shp``."""
    fratelli = [p for p in shp.parent.glob("*.shp") if p.is_file()]
    base = shp.parent.name if len(fratelli) == 1 else f"{shp.parent.name}_{shp.stem}"
    return _identificatore(base)


def shapefile(dove: Path) -> list[Path]:
    """Gli shapefile che Limen legge, in ordine stabile."""
    cartelle = (c for schema in _CARTELLE for c in dove.glob(schema))
    return sorted(shp for cartella in cartelle for shp in cartella.glob("*.shp"))


def _impronta(shp: Path) -> str:
    parti = [shp, shp.with_suffix(".dbf")]
    return ";".join(f"{p.stat().st_mtime_ns}:{p.stat().st_size}" for p in parti if p.exists())


@dataclass(frozen=True, slots=True)
class _Info:
    srid: int
    colonne: list[str]
    forme: int


def _leggi_info(shp: Path) -> _Info:
    import pyogrio
    import pyproj

    info = pyogrio.read_info(shp)
    srid = pyproj.CRS.from_user_input(info["crs"]).to_epsg()
    if srid is None:
        raise ValueError(f"{shp.name}: sistema di riferimento senza codice EPSG ({info['crs']})")
    return _Info(srid=int(srid), colonne=list(info["fields"]), forme=int(info["features"]))


def _testo(valore: Any) -> str | None:
    if hasattr(valore, "item"):
        # Prima di tutto: `numpy.float64` è anche un `float`, e con numpy 2 il
        # suo repr è «np.float64(4.5)».
        valore = valore.item()
    if valore is None:
        return None
    if isinstance(valore, float):
        if valore != valore:  # NaN: un numero mancante nel dbf
            return None
        return str(int(valore)) if valore.is_integer() else repr(valore)
    testo = str(valore)
    return testo or None


def _blocco(shp: Path, primo: int, quanti: int) -> list[tuple[Any, ...]]:
    """Righe ``(fid, wkb, attributi…)`` delle forme ``[primo, primo+quanti)``."""
    import numpy as np
    from pyogrio.raw import read

    _, _, geometrie, campi = read(shp, fids=np.arange(primo, primo + quanti))
    return [
        (primo + i + 1, bytes(geometrie[i]), *(_testo(c[i]) for c in campi))
        for i in range(len(geometrie))
        if geometrie[i] is not None
    ]


def _blocchi(forme: int) -> Iterator[tuple[int, int]]:
    for primo in range(0, forme, LOTTO):
        yield primo, min(LOTTO, forme - primo)


async def _carica(conn: asyncpg.Connection, shp: Path, tabella: str, impronta: str) -> int:
    info = await asyncio.to_thread(_leggi_info, shp)
    colonne = [_identificatore(c, accorcia=False) for c in info.colonne]
    nuova = f"_nuova_{hashlib.md5(tabella.encode(), usedforsecurity=False).hexdigest()[:12]}"
    definizioni = ", ".join(f'"{c}" text' for c in colonne)
    elenco = ", ".join(f'"{c}"' for c in colonne)
    async with conn.transaction():
        await conn.execute(f'DROP TABLE IF EXISTS {SCHEMA}."{nuova}"')
        await conn.execute(
            f'CREATE TABLE {SCHEMA}."{nuova}" (fid integer PRIMARY KEY, '
            f"geom geometry(Geometry, 4326){', ' + definizioni if colonne else ''})"
        )
        await conn.execute(
            f"CREATE TEMP TABLE _carico (fid integer, wkb bytea"
            f"{', ' + definizioni if colonne else ''}) ON COMMIT DROP"
        )
        righe = 0
        for primo, quanti in _blocchi(info.forme):
            blocco = await asyncio.to_thread(_blocco, shp, primo, quanti)
            await conn.copy_records_to_table("_carico", records=blocco, timeout=_TIMEOUT_S)
            await conn.execute(
                f'INSERT INTO {SCHEMA}."{nuova}" (fid, geom{", " + elenco if colonne else ""}) '
                f"SELECT fid, ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromWKB(wkb), $1), 4326))"
                f"{', ' + elenco if colonne else ''} FROM _carico",
                info.srid,
                timeout=_TIMEOUT_S,
            )
            await conn.execute("TRUNCATE _carico")
            righe += len(blocco)
        await conn.execute(
            f'CREATE INDEX ON {SCHEMA}."{nuova}" USING gist (geom)', timeout=_TIMEOUT_S
        )
        # Lo scambio aspetta chi sta leggendo la tabella vecchia (lo sweep, un
        # geoserver-sync): con i 30 s del pool annullerebbe tutto il carico.
        await conn.execute(f'DROP TABLE IF EXISTS {SCHEMA}."{tabella}"', timeout=_TIMEOUT_S)
        await conn.execute(
            f'ALTER TABLE {SCHEMA}."{nuova}" RENAME TO "{tabella}"', timeout=_TIMEOUT_S
        )
        await conn.execute(f'COMMENT ON TABLE {SCHEMA}."{tabella}" IS $${impronta}$$')
    return righe


async def _impronta_caricata(conn: asyncpg.Connection, tabella: str) -> str | None:
    valore = await conn.fetchval(
        "SELECT obj_description(to_regclass($1), 'pg_class')", f'{SCHEMA}."{tabella}"'
    )
    return None if valore is None else str(valore)


@dataclass
class Esito:
    caricate: dict[str, int]
    invariate: list[str]
    fallite: dict[str, str]


async def carica_vettori(dove: Path, *, forza: bool = False, scelti: Sequence[Path] = ()) -> Esito:
    """Carica gli shapefile di ``dove`` nello schema ``sorgenti``; uno che fallisce non
    ferma gli altri."""
    esito = Esito(caricate={}, invariate=[], fallite={})
    for shp in scelti or shapefile(dove):
        tabella = nome_tabella(shp)
        impronta = _impronta(shp)
        async with acquire() as conn:
            if not forza and await _impronta_caricata(conn, tabella) == impronta:
                esito.invariate.append(tabella)
                continue
            try:
                righe = await _carica(conn, shp, tabella, impronta)
            except (OSError, ValueError, asyncpg.PostgresError) as exc:
                # `TimeoutError` è un OSError senza messaggio: senza il tipo,
                # nel log resterebbe un errore vuoto.
                motivo = f"{type(exc).__name__}: {exc}"[:300]
                log.warning("vettori.fallito", file=shp.name, error=motivo)
                esito.fallite[tabella] = motivo
                continue
        esito.caricate[tabella] = righe
        log.info("vettori.caricato", tabella=tabella, righe=righe)
    log.info(
        "vettori.fatto",
        caricate=len(esito.caricate),
        invariate=len(esito.invariate),
        fallite=len(esito.fallite),
    )
    return esito


__all__ = ["SCHEMA", "Esito", "carica_vettori", "nome_tabella", "shapefile"]
