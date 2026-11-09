"""Pacchetto rapido: i fattori per cella in tre file, uno per licenza (#406).

Lo snapshot della #305 è un dump unico per un'istanza propria. Il pacchetto è
la sua versione **pubblicabile**: un asset della release che chiunque scarica
al posto dei ~25 GB di sorgenti e delle ~7 ore di calcolo. Ridistribuisce dati
derivati, e le licenze delle fonti non si possono mescolare:

* **ISPRA, CC BY-SA 4.0** — le colonne da IFFI, PAI e mosaico idraulico.
  Lo share-alike, in un file comune, renderebbe BY-SA anche il resto;
* **OSM, ODbL 1.0** — le distanze dalla rete stradale e ferroviaria. Non è
  compatibile con il BY-SA, quindi non sta nemmeno con ISPRA;
* **CC BY 4.0** — DTM, CORINE (e ciò che ne deriva: WUI, vicinanza urbana),
  impermeabilizzazione CLMS e lo storico FIRMS.

Resta **fuori**, e si ricalcola sul server che importa:

* la litologia: la licenza del Geoportale MASE dice CC BY 4.0 per il servizio
  di Download, ma le stesse note legali parlano di «soli fini istituzionali».
  Nel dubbio non la si ridistribuisce; la carta è 1:500.000 e costa minuti;
* le colonne che mescolano licenze (``s_static``, ``exposure_norm``): le
  ricalcola ``limen calibrate``, che dopo l'import va lanciato comunque;
* ``flood_hazard_subdiv``: si ricava dal mosaico ISPRA (0,7 GB), che il server
  scarica per disegnare la mappa;
* lo stato della catena FWI: dopo ``fwi.max_gap_days`` (5 giorni) uno stato
  vecchio si scarta, quindi in una release sarebbe già inutile. Lo ricostruisce
  ``limen fwi-backfill`` dall'archivio.

Il formato è **CSV compresso da COPY**, non ``pg_dump``: un dump porta tabelle
intere, e qui una tabella si divide per colonne. ``COPY (SELECT …)`` sceglie le
colonne, non chiede i binari di PostgreSQL sul client, e il file si apre con
qualunque strumento — che per un dato ridistribuito sotto licenza aperta conta.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import asyncpg

from limen import __version__
from limen.config.catalogo_dati import CatalogoDati
from limen.core.logging import get_logger
from limen.data.backup import BackupError, _conta, _livello, _sha256
from limen.data.dcat import dcat_ap_it
from limen.data.static_snapshot import _griglia
from limen.integrations._http import SharedHttpClient, call_with_retry, fetch_with_retry
from limen.integrations.static_bootstrap.fingerprint import SOURCE as BOOTSTRAP_SOURCE
from limen.integrations.static_bootstrap.fingerprint import STEP_VERSION

log = get_logger(__name__)

MANIFEST = "manifest.json"
DCAT = "catalogo-dcat-ap_it.ttl"
TABELLA = "public.cell_static_factors"
CHIAVE = "cell_id"


@dataclass(frozen=True, slots=True)
class Risorsa:
    """Un file del pacchetto: una licenza, le sue colonne, le sue citazioni."""

    id: str
    licenza: str
    url_licenza: str
    #: Le voci di ``config/dati.yaml`` da cui vengono le colonne.
    voci: tuple[str, ...]
    colonne: tuple[str, ...]
    #: Tabelle intere che viaggiano con questa licenza.
    tabelle: tuple[str, ...] = ()
    #: Citazioni di fonti che il catalogo non elenca come voce.
    citazioni: tuple[str, ...] = field(default=())


RISORSE: tuple[Risorsa, ...] = (
    Risorsa(
        id="ispra-by-sa",
        licenza="CC BY-SA 4.0",
        url_licenza="https://creativecommons.org/licenses/by-sa/4.0/",
        voci=("iffi", "pai_frana", "idraulica"),
        colonne=(
            "distance_to_iffi_m",
            "iffi_density_500",
            "pai_class_norm",
            "flood_hazard_class",
            "flood_hazard_norm",
        ),
    ),
    Risorsa(
        id="osm-odbl",
        licenza="ODbL 1.0",
        url_licenza="https://opendatacommons.org/licenses/odbl/1-0/",
        voci=("strade",),
        colonne=("distance_to_road_m", "distance_to_rail_m", "nearest_road_class"),
    ),
    Risorsa(
        id="cc-by",
        licenza="CC BY 4.0",
        url_licenza="https://creativecommons.org/licenses/by/4.0/",
        voci=("dtm", "quota_sul_fondo", "corine", "wui", "vicinanza", "impermeabilizzazione"),
        colonne=(
            "slope_deg",
            "aspect_deg",
            "elevation_m",
            "quota_sul_fondo_m",
            "twi",
            "curvature",
            "landuse_code",
            "land_cover",
            "near_urban",
            "near_infra",
            "wui_proximity_norm",
            "imperviousness_norm",
            "fire_density",
        ),
        tabelle=("public.fire_events",),
        citazioni=(
            "Storico degli incendi (fire_events, fire_density): NASA FIRMS, CC0. "
            "We acknowledge the use of data from NASA LANCE FIRMS "
            "(https://earthdata.nasa.gov/firms), part of NASA ESDIS.",
        ),
    ),
)

#: Colonne di ``cell_static_factors`` che il pacchetto non porta, e perché.
#: Una colonna nuova che non è né qui né in una risorsa ferma l'export: deve
#: essere una scelta, non un file sbagliato per distrazione.
ESCLUSE: dict[str, str] = {
    "lithology": "carta geolitologica MASE: licenza ambigua, si ricalcola in locale",
    "litho_weight": "carta geolitologica MASE: licenza ambigua, si ricalcola in locale",
    "dist_faults_m": "carta geolitologica MASE: licenza ambigua, si ricalcola in locale",
    "s_static": "mescola licenze diverse: la ricalcola limen calibrate",
    "exposure_norm": "mescola licenze diverse: la ricalcola limen calibrate",
    "extras": "metadati locali",
    "updated_at": "si scrive all'import",
    "population_count": "nessun passo la riempie",
    "buildings_count": "nessun passo la riempie",
    "infra_density_norm": "nessun passo la riempie",
}

#: Passi del bootstrap le cui colonne non viaggiano: la loro impronta resta
#: fuori dal pacchetto, così il server che importa li ricalcola.
PASSI_ESCLUSI = frozenset({"geological"})


def non_assegnate(colonne: Iterable[str]) -> list[str]:
    """Le colonne della tabella che nessuna risorsa porta e nessuna esclusione spiega."""
    note = {CHIAVE, *ESCLUSE, *(c for r in RISORSE for c in r.colonne)}
    return sorted(c for c in colonne if c not in note)


def attribuzioni(risorsa: Risorsa, catalogo: CatalogoDati, *, versione: str) -> str:
    """Il file ``ATTRIBUZIONI`` di una risorsa, dalle voci del catalogo."""
    righe = [
        f"Limen {versione} — pacchetto di dati statici, risorsa «{risorsa.id}».",
        f"Licenza: {risorsa.licenza} ({risorsa.url_licenza}).",
        "",
        "Valori per cella (griglia di 1 km) calcolati da Limen a partire dalle fonti",
        "qui sotto: sono dati modificati, non i dati originali.",
        "",
    ]
    for id_ in risorsa.voci:
        voce = catalogo.voce(id_)
        righe.append(f"- {voce.nome}: {voce.fonte}")
        if voce.attribuzione:
            righe.append(f"  {voce.attribuzione}")
        if voce.url:
            righe.append(f"  {voce.url}")
    righe.extend(f"- {c}" for c in risorsa.citazioni)
    righe += ["", "Colonne: " + ", ".join(risorsa.colonne)]
    if risorsa.tabelle:
        righe.append("Tabelle: " + ", ".join(risorsa.tabelle))
    return "\n".join(righe) + "\n"


def _nome_dati(risorsa: Risorsa, tabella: str = TABELLA) -> str:
    return f"{risorsa.id}.{tabella.split('.', 1)[1]}.csv.gz"


def _nome_attribuzioni(risorsa: Risorsa) -> str:
    return f"ATTRIBUZIONI-{risorsa.id}.txt"


async def _colonne(conn: asyncpg.Connection, tabella: str) -> list[str]:
    schema, nome = tabella.split(".", 1)
    righe = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = $1 AND table_name = $2 ORDER BY ordinal_position",
        schema,
        nome,
    )
    return [str(r["column_name"]) for r in righe]


async def _copia_fuori(conn: asyncpg.Connection, query: str, dest: Path) -> None:
    with gzip.open(dest, "wb", compresslevel=6) as gz:

        async def scrivi(blocco: bytes) -> None:
            gz.write(blocco)

        await conn.copy_from_query(query, output=scrivi, format="csv", header=True)


async def esporta_pacchetto(
    *,
    conn: asyncpg.Connection,
    catalogo: CatalogoDati,
    uscita: Path,
    adesso: datetime,
    url_base: str | None = None,
) -> dict[str, Any]:
    """Scrive il pacchetto in ``uscita`` e ne restituisce il manifest."""
    uscita.mkdir(parents=True, exist_ok=True)
    file: dict[str, dict[str, Any]] = {}
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        orfane = non_assegnate(await _colonne(conn, TABELLA))
        if orfane:
            raise BackupError(
                f"colonne senza licenza assegnata: {', '.join(orfane)} "
                "(aggiungile a una risorsa o a ESCLUSE in pacchetto_statico.py)"
            )
        righe = await _conta(conn, [TABELLA, *(t for r in RISORSE for t in r.tabelle)])
        if not righe[TABELLA]:
            raise BackupError("cell_static_factors è vuota: niente da esportare")
        migrazioni = await _livello(conn)
        griglia = await _griglia(conn)
        impronte = [
            dict(r)
            for r in await conn.fetch(
                """
                SELECT dataset, version, metadata::text AS metadata
                  FROM dataset_versions WHERE source = $1 ORDER BY dataset, fetched_at
                """,
                BOOTSTRAP_SOURCE,
            )
            if str(r["dataset"]).split(":", 1)[0] not in PASSI_ESCLUSI
        ]
        for risorsa in RISORSE:
            nome = _nome_dati(risorsa)
            colonne = ", ".join((CHIAVE, *risorsa.colonne))
            await _copia_fuori(
                conn,
                f"SELECT {colonne} FROM {TABELLA} ORDER BY {CHIAVE}",
                uscita / nome,
            )
            file[nome] = {
                "risorsa": risorsa.id,
                "tabella": TABELLA,
                "colonne": [CHIAVE, *risorsa.colonne],
                "righe": righe[TABELLA],
            }
            for tabella in risorsa.tabelle:
                nome = _nome_dati(risorsa, tabella)
                colonne_t = await _colonne(conn, tabella)
                await _copia_fuori(
                    conn,
                    f"SELECT {', '.join(colonne_t)} FROM {tabella} ORDER BY 1, 2",
                    uscita / nome,
                )
                file[nome] = {
                    "risorsa": risorsa.id,
                    "tabella": tabella,
                    "colonne": colonne_t,
                    "righe": righe[tabella],
                }
    for risorsa in RISORSE:
        nome = _nome_attribuzioni(risorsa)
        (uscita / nome).write_text(
            attribuzioni(risorsa, catalogo, versione=__version__), encoding="utf-8"
        )
        file[nome] = {"risorsa": risorsa.id}
    for nome, voce in file.items():
        percorso = uscita / nome
        voce["byte"] = percorso.stat().st_size
        voce["sha256"] = await asyncio.to_thread(_sha256, percorso)
    manifest: dict[str, Any] = {
        "limen": __version__,
        "creato": adesso.astimezone(UTC).isoformat(),
        "migrazioni": migrazioni,
        "step_version": dict(STEP_VERSION),
        "passi_esclusi": sorted(PASSI_ESCLUSI),
        "colonne_escluse": ESCLUSE,
        "licenze": {r.id: r.licenza for r in RISORSE},
        "griglia": griglia,
        "impronte": impronte,
        "file": file,
    }
    # I metadati per i cataloghi (#504) descrivono i file con dimensione e
    # SHA-256, quindi vengono dopo di loro; il manifest li nomina e resta l'ultimo.
    (uscita / DCAT).write_text(
        dcat_ap_it(manifest, catalogo, risorse=RISORSE, url_base=url_base), encoding="utf-8"
    )
    manifest["metadati"] = {"dcat-ap_it": DCAT}
    # Il manifest per ultimo: è lui a dire che il pacchetto è completo.
    (uscita / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log.info(
        "pacchetto_statico.esportato",
        uscita=str(uscita),
        byte=sum(int(v["byte"]) for v in file.values()),
        celle=righe[TABELLA],
        aoi=len(griglia),
    )
    return manifest


async def _scarica(url: str, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    client = await SharedHttpClient.get()
    async with client.stream("GET", url) as risposta:
        risposta.raise_for_status()
        with tmp.open("wb") as f:
            async for blocco in risposta.aiter_bytes(1 << 20):
                await asyncio.to_thread(f.write, blocco)
    tmp.replace(dest)


async def scarica_pacchetto(url_manifest: str, cartella: Path) -> dict[str, Any]:
    """Scarica manifest e file accanto a ``url_manifest``, verificando gli sha256."""
    cartella.mkdir(parents=True, exist_ok=True)
    risposta = await fetch_with_retry("GET", url_manifest)
    risposta.raise_for_status()
    manifest: dict[str, Any] = risposta.json()
    base = url_manifest.rsplit("/", 1)[0]
    for nome, voce in manifest["file"].items():
        dest = cartella / nome
        if not (dest.exists() and await asyncio.to_thread(_sha256, dest) == voce["sha256"]):
            await call_with_retry(partial(_scarica, f"{base}/{nome}", dest))
        log.info("pacchetto_statico.scaricato", file=nome, byte=voce["byte"])
    (cartella / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def verifica(cartella: Path, manifest: dict[str, Any]) -> None:
    """Ogni file c'è e ha lo sha256 del manifest, o :class:`BackupError`."""
    for nome, voce in manifest["file"].items():
        percorso = cartella / nome
        if not percorso.exists():
            raise BackupError(f"{nome}: manca nel pacchetto")
        if _sha256(percorso) != voce["sha256"]:
            raise BackupError(f"{nome}: lo sha256 non è quello del manifest")


async def importa_pacchetto(
    *, conn: asyncpg.Connection, cartella: Path, forza: bool = False
) -> dict[str, int]:
    """Carica il pacchetto di ``cartella`` in una sola transazione.

    Stessi controlli dello snapshot della #305 — migrazione, griglia per AOI,
    fattori già presenti — più gli sha256. Le impronte dei passi inclusi
    tornano, quelle dei passi esclusi no: il bootstrap che segue ricalcola
    solo la litologia.
    """
    manifest: dict[str, Any] = json.loads((cartella / MANIFEST).read_text(encoding="utf-8"))
    await asyncio.to_thread(verifica, cartella, manifest)
    livello = await _livello(conn)
    if livello != manifest["migrazioni"]:
        raise BackupError(
            f"il database è alla migrazione {livello}, il pacchetto a "
            f"{manifest['migrazioni']}: aggiorna (limen migrate) o prendi un pacchetto più recente"
        )
    qui = await _griglia(conn)
    diverse = [aoi for aoi, g in manifest["griglia"].items() if qui.get(aoi) != g]
    if diverse:
        raise BackupError(
            f"griglia diversa da quella del pacchetto in {len(diverse)} AOI "
            f"({', '.join(sorted(diverse)[:5])}): lancia prima limen seed"
        )
    gia = (await _conta(conn, [TABELLA]))[TABELLA]
    if gia and not forza:
        raise BackupError(f"cell_static_factors ha già {gia} righe: il pacchetto le sostituirebbe")

    dati = {n: v for n, v in manifest["file"].items() if "tabella" in v}
    fattori = [(n, v) for n, v in dati.items() if v["tabella"] == TABELLA]
    altre = [(n, v) for n, v in dati.items() if v["tabella"] != TABELLA]
    async with conn.transaction():
        appoggi: list[tuple[str, list[str]]] = []
        for i, (nome, voce) in enumerate(fattori):
            appoggio = f"_pacchetto_{i}"
            colonne = list(voce["colonne"])
            await conn.execute(
                f"CREATE TEMP TABLE {appoggio} ON COMMIT DROP AS "
                f"SELECT {', '.join(colonne)} FROM {TABELLA} LIMIT 0"
            )
            await _copia_dentro(conn, cartella / nome, appoggio, colonne)
            appoggi.append((appoggio, colonne))
        await conn.execute(f"TRUNCATE {TABELLA}")
        await conn.execute(
            "DELETE FROM public.dataset_versions WHERE source = $1", BOOTSTRAP_SOURCE
        )
        primo = appoggi[0][0]
        tutte = [c for _, colonne in appoggi for c in colonne if c != CHIAVE]
        join = " ".join(f"JOIN {a} USING ({CHIAVE})" for a, _ in appoggi[1:])
        await conn.execute(
            f"INSERT INTO {TABELLA} ({CHIAVE}, {', '.join(tutte)}) "
            f"SELECT {primo}.{CHIAVE}, {', '.join(tutte)} FROM {primo} {join}"
        )
        for nome, voce in altre:
            await conn.execute(f"TRUNCATE {voce['tabella']}")
            await _copia_dentro(conn, cartella / nome, voce["tabella"], list(voce["colonne"]))
        trovate = await _conta(conn, [str(v["tabella"]) for v in dati.values()])
        for voce in dati.values():
            if trovate[voce["tabella"]] != voce["righe"]:
                raise BackupError(
                    f"{voce['tabella']}: {trovate[voce['tabella']]} righe caricate, "
                    f"il manifest ne dice {voce['righe']} — nessun dato toccato"
                )
        if manifest["impronte"]:
            await conn.executemany(
                "INSERT INTO public.dataset_versions (source, dataset, version, metadata) "
                "VALUES ($1, $2, $3, $4::jsonb)",
                [
                    (BOOTSTRAP_SOURCE, i["dataset"], i["version"], i["metadata"])
                    for i in manifest["impronte"]
                ],
            )
    log.info(
        "pacchetto_statico.importato",
        righe=trovate,
        impronte=len(manifest["impronte"]),
        hint="poi limen bootstrap-static (litologia) e limen calibrate (s_static, esposizione)",
    )
    return trovate


async def _copia_dentro(
    conn: asyncpg.Connection, sorgente: Path, tabella: str, colonne: list[str]
) -> None:
    schema, nome = tabella.split(".", 1) if "." in tabella else (None, tabella)
    with gzip.open(sorgente, "rb") as gz:
        await conn.copy_to_table(
            nome, source=gz, schema_name=schema, columns=colonne, format="csv", header=True
        )


__all__ = [
    "ESCLUSE",
    "MANIFEST",
    "PASSI_ESCLUSI",
    "RISORSE",
    "Risorsa",
    "attribuzioni",
    "esporta_pacchetto",
    "importa_pacchetto",
    "non_assegnate",
    "scarica_pacchetto",
    "verifica",
]
