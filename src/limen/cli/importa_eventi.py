"""``limen importa-eventi FILE --ente NOME --licenza LICENZA`` — gli eventi
datati di un ente nel registro (#509, epica #345).

Il denominatore è il collo di bottiglia: un evento entrava in
``verifiche_eventi`` solo dal fact check a mano o dalla raccolta della stampa,
e gli elenchi degli enti — interventi di Protezione civile, frane rilevate dai
tecnici, aree allagate viste a terra — non avevano un formato con cui arrivare.
Il formato è quello di ``docs/guida/partecipare.md``, ricalcato su e-ITALICA:
una riga per evento, CSV (virgola o punto e virgola) o GeoJSON di punti.

Un evento di un ente è verità senza seconda fonte: la fonte è l'ente, e la sua
licenza viaggia con ogni riga in ``fonti``. Ogni riga passa dalla stessa misura
e dalle stesse regole dell'esito della raccolta (``anticipo.sql``,
``core.verifiche.esito``); un evento più vecchio dello storico delle previsioni
resta ``non_verificabile`` nel registro, e se è una frana entra comunque nel
truth set del backtest (``landslide_events``, ``source = 'ente'``).

Idempotente due volte: lo stesso file (stesso ente e licenza) si riconosce
dall'impronta in ``dataset_versions`` e non si rilegge; un file che cresce
misura solo le righe nuove, perché una riga già registrata tiene la misura
congelata allora — rimisurarla giorni dopo leggerebbe un fondo già cancellato
dalla retention.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from shapely.geometry import Point

from limen.agents.chat_agents.estrattore_eventi import NOME_PERICOLO
from limen.cli.registra_verifica import frana_da_verifica
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.verifiche.esito import esito
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import anticipo_repo, dataset_versions_repo, verifiche_eventi_repo
from limen.data.repos.landslide_events_repo import LandslideEvent
from limen.data.repos.landslide_events_repo import upsert_many as landslide_upsert
from limen.data.repos.verifiche_eventi_repo import VerificaEvento

log = get_logger(__name__)

SORGENTE_ENTE = "ente"
_ROMA = ZoneInfo("Europe/Rome")
_PERICOLO = {
    "frana": HazardType.LANDSLIDE,
    "alluvione": HazardType.FLOOD,
    "incendio": HazardType.WILDFIRE,
    **{h.value: h for h in HazardType},
}
#: L'ora convenzionale di un evento datato al solo giorno, come nel fact check.
_MEZZOGIORNO = time(12)


class FormatoNonValidoError(ValueError):
    """Il file non rispetta il formato: un messaggio per riga sbagliata."""

    def __init__(self, errori: list[str]) -> None:
        super().__init__("; ".join(errori))
        self.errori = errori


class RigaEnte(BaseModel):
    """Una riga del file, con i nomi delle colonne del formato."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    pericolo: HazardType
    data: date
    ora: time | None = None
    precisione_ora: Literal["T1", "T2", "T3"] | None = None
    comuni: list[str] = Field(min_length=1)
    luogo: str = Field(min_length=1)
    regione: str | None = None
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    precisione_luogo: Literal["P0", "P1", "P10", "P100"] | None = None
    tipo: str | None = None
    fonte: str = Field(min_length=1)
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _vuoti(cls, dati: Any) -> Any:
        # Una cella vuota del foglio di calcolo è un campo assente, non una stringa.
        if isinstance(dati, dict):
            return {k: v for k, v in dati.items() if v not in ("", None)}
        return dati

    @field_validator("pericolo", mode="before")
    @classmethod
    def _pericolo(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip().lower() in _PERICOLO:
            return _PERICOLO[v.strip().lower()]
        raise ValueError("pericolo: frana, alluvione o incendio")

    @field_validator("comuni", mode="before")
    @classmethod
    def _comuni(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = re.split(r"[;,\s]+", v.strip())
        codici = [str(c).strip().zfill(6) for c in v if str(c).strip()]
        if not all(c.isdigit() and len(c) == 6 for c in codici):
            raise ValueError("comuni: codici ISTAT a sei cifre, separati da punto e virgola")
        return codici

    @model_validator(mode="after")
    def _coerente(self) -> Self:
        if (self.lon is None) != (self.lat is None):
            raise ValueError("lon e lat vanno insieme")
        if self.lon is not None and self.precisione_luogo is None:
            raise ValueError("un punto vuole la sua precisione_luogo (P0, P1, P10, P100)")
        if self.precisione_ora == "T1" and self.ora is None:
            raise ValueError("precisione_ora T1 vuole l'ora")
        return self

    @property
    def quando(self) -> tuple[datetime, str]:
        precisione = self.precisione_ora or ("T1" if self.ora is not None else "T3")
        return datetime.combine(self.data, self.ora or _MEZZOGIORNO, tzinfo=_ROMA), precisione


def _norma(testo: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


def _righe_csv(testo: str) -> list[dict[str, Any]]:
    prima = testo.splitlines()[0] if testo else ""
    # Excel in italiano salva con il punto e virgola.
    sep = ";" if prima.count(";") > prima.count(",") else ","
    return list(csv.DictReader(io.StringIO(testo), delimiter=sep))


def _righe_geojson(testo: str) -> list[dict[str, Any]]:
    fc = json.loads(testo)
    if fc.get("type") != "FeatureCollection":
        raise FormatoNonValidoError(["il GeoJSON deve essere una FeatureCollection"])
    righe: list[dict[str, Any]] = []
    for f in fc.get("features") or []:
        props = dict(f.get("properties") or {})
        geom = f.get("geometry")
        if geom is not None:
            if geom.get("type") != "Point":
                # Il registro tiene un punto: un poligono preso per centroide
                # spaccerebbe per esatto un luogo che non lo è.
                props["_geometria"] = geom.get("type")
            else:
                props["lon"], props["lat"] = geom["coordinates"][:2]
        righe.append(props)
    return righe


def leggi_file(path: Path) -> list[RigaEnte]:
    testo = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in (".geojson", ".json"):
        grezze = _righe_geojson(testo)
    else:
        grezze = _righe_csv(testo)
    righe: list[RigaEnte] = []
    errori: list[str] = []
    # Riga 2 del CSV è il primo evento: la 1 è l'intestazione.
    for n, grezza in enumerate(grezze, start=2):
        if "_geometria" in grezza:
            errori.append(f"riga {n}: geometria {grezza['_geometria']}, serve un Point")
            continue
        try:
            righe.append(RigaEnte.model_validate(grezza))
        except ValidationError as exc:
            for e in exc.errors():
                campo = ".".join(str(x) for x in e["loc"]) or "riga"
                errori.append(f"riga {n}: {campo}: {e['msg']}")
    doppi = [k for k, c in Counter(r.id for r in righe).items() if c > 1]
    errori += [f"id ripetuto: {k}" for k in doppi]
    if not righe and not errori:
        errori.append("nessun evento nel file")
    if errori:
        raise FormatoNonValidoError(errori)
    return righe


def slug(riga: RigaEnte, ente: str) -> str:
    """``AAAA-MM-GG-<pericolo>-ente-<ente>-<id>``: l'id dell'ente tiene lo
    slug stabile quando il file cresce o cambia ordine."""
    pericolo = NOME_PERICOLO[riga.pericolo]
    return f"{riga.data.isoformat()}-{pericolo}-ente-{_norma(ente)}-{_norma(riga.id)}"


def verifica_da_riga(
    riga: RigaEnte, *, ente: str, licenza: str, misura: dict[str, Any]
) -> VerificaEvento:
    evento_at, precisione = riga.quando
    risultato, motivo = esito(misura)
    fonte: dict[str, Any] = {"ente": ente, "licenza": licenza, "id": riga.id, "fonte": riga.fonte}
    if riga.fonte.startswith(("http://", "https://")):
        fonte["url"] = riga.fonte
    if riga.tipo:
        fonte["tipo"] = riga.tipo
    return VerificaEvento(
        slug=slug(riga, ente),
        hazard=riga.pericolo,
        esito=risultato,
        motivo=motivo,
        evento_at=evento_at,
        precisione_ora=precisione,
        luogo=riga.luogo,
        regione=riga.regione,
        comuni=tuple(riga.comuni),
        punto=Point(riga.lon, riga.lat) if riga.lon is not None and riga.lat is not None else None,
        precisione_luogo=riga.precisione_luogo,
        fonti=(fonte,),
        misura=misura,
    )


async def run(path: str, *, ente: str, licenza: str) -> int:
    p = Path(path)
    try:
        righe = leggi_file(p)
    except FormatoNonValidoError as exc:
        for e in exc.errori:
            log.error("importa_eventi.formato", path=path, errore=e)
        return 2
    except (OSError, ValueError) as exc:
        log.error("importa_eventi.file_non_leggibile", path=path, error=str(exc))
        return 2

    dataset = _norma(ente)
    impronta = dataset_versions_repo.content_hash([p.read_bytes(), ente.encode(), licenza.encode()])
    async with lifespan_pool():
        await run_migrations()
        if await dataset_versions_repo.find(SORGENTE_ENTE, dataset, impronta) is not None:
            log.info("importa_eventi.gia_importato", ente=ente, path=path)
            return 0
        codici = sorted({c for r in righe for c in r.comuni})
        ignoti = sorted(set(codici) - await verifiche_eventi_repo.comuni_noti(codici))
        if ignoti:
            log.error("importa_eventi.comuni_ignoti", codici=ignoti)
            return 2

        esiti: Counter[str] = Counter()
        frane: list[LandslideEvent] = []
        for r in righe:
            if await verifiche_eventi_repo.esiste(slug(r, ente)):
                esiti["gia_registrato"] += 1
                continue
            evento_at, precisione = r.quando
            misura = await anticipo_repo.misura(
                comuni=r.comuni,
                hazard=r.pericolo,
                evento_at=evento_at,
                tolleranza_ore=24 if precisione == "T3" else 12,
            )
            v = verifica_da_riga(r, ente=ente, licenza=licenza, misura=misura)
            luogo = await verifiche_eventi_repo.upsert(v)
            esiti[v.esito] += 1
            if v.hazard is HazardType.LANDSLIDE and luogo is not None:
                frane.append(frana_da_verifica(v, *luogo, sorgente=SORGENTE_ENTE))
        await landslide_upsert(frane)
        await dataset_versions_repo.record(
            source=SORGENTE_ENTE,
            dataset=dataset,
            version=impronta,
            metadata={
                "ente": ente,
                "licenza": licenza,
                "file": p.name,
                "righe": len(righe),
                **esiti,
            },
        )
    log.info("importa_eventi.done", ente=ente, righe=len(righe), frane=len(frane), **esiti)
    return 0
