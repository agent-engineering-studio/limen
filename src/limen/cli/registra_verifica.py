"""``limen registra-verifica FILE...`` — un evento verificato entra nel registro.

Il fact check (skill ``limen-fact-check``) decide se un evento è successo e
quanto prima Limen lo aveva visto; questo comando ne salva il risultato,
qualunque sia l'esito, in ``verifiche_eventi`` (migrazione 074), con la misura
di anticipo.sql congelata prima che la retention di ``risk_assessments`` la
cancelli. Una frana va anche in ``landslide_events`` con ``source = 'stampa'``:
il backtest la legge accanto a ITALICA.

Un'alluvione dalla stampa resta solo nel registro: ``flood_events`` vuole il
perimetro osservato, e un comune preso per area allagata è l'errore che la
migrazione 040 documenta.

Idempotente: la chiave è lo slug, rieseguire riscrive la stessa riga.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from shapely.geometry import Point

from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import verifiche_eventi_repo
from limen.data.repos.landslide_events_repo import LandslideEvent
from limen.data.repos.landslide_events_repo import upsert_many as landslide_upsert
from limen.data.repos.verifiche_eventi_repo import VerificaEvento

log = get_logger(__name__)

SORGENTE_STAMPA = "stampa"


class _Evento(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quando: datetime
    precisione_ora: Literal["T1", "T2", "T3"]
    luogo: str = Field(min_length=1)
    regione: str | None = None
    comuni: list[str] = Field(min_length=1)
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    precisione_luogo: Literal["P0", "P1", "P10", "P100"] | None = None

    @model_validator(mode="after")
    def _punto_intero(self) -> Self:
        if self.quando.tzinfo is None:
            raise ValueError("evento.quando senza fuso: l'ora italiana va dichiarata")
        if (self.lon is None) != (self.lat is None):
            raise ValueError("evento.lon e evento.lat vanno insieme")
        if self.lon is not None and self.precisione_luogo is None:
            raise ValueError("un punto dalla notizia vuole la sua precisione_luogo")
        return self


class _Registro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1)
    pericolo: HazardType
    esito: Literal["anticipata", "contemporanea", "mancata", "non_verificabile"]
    motivo: str | None = None
    evento: _Evento
    fonti: list[dict[str, Any]] = Field(min_length=1)
    misura: dict[str, Any]


def leggi(path: Path) -> VerificaEvento:
    """Valida il file del fact check e lo traduce nella riga del registro."""
    r = _Registro.model_validate_json(path.read_text(encoding="utf-8"))
    e = r.evento
    return VerificaEvento(
        slug=r.slug,
        hazard=r.pericolo,
        esito=r.esito,
        motivo=r.motivo,
        evento_at=e.quando,
        precisione_ora=e.precisione_ora,
        luogo=e.luogo,
        regione=e.regione,
        comuni=tuple(e.comuni),
        punto=Point(e.lon, e.lat) if e.lon is not None and e.lat is not None else None,
        precisione_luogo=e.precisione_luogo,
        fonti=tuple(r.fonti),
        misura=r.misura,
    )


def frana_da_verifica(v: VerificaEvento, punto: Point, precisione: str) -> LandslideEvent:
    return LandslideEvent(
        id=f"{SORGENTE_STAMPA}:{v.slug}",
        source=SORGENTE_STAMPA,
        event_time=v.evento_at,
        geom=punto,
        temporal_accuracy=v.precisione_ora,
        geographic_accuracy=precisione,
        region=v.regione,
        municipality=v.luogo,
        attributes={
            "slug": v.slug,
            "comuni": list(v.comuni),
            "fonti": [f.get("url") for f in v.fonti if f.get("url")],
        },
    )


async def run(paths: list[str]) -> int:
    verifiche: list[VerificaEvento] = []
    for p in paths:
        try:
            verifiche.append(leggi(Path(p)))
        except (OSError, ValidationError) as exc:
            log.error("registra_verifica.file_non_valido", path=p, error=str(exc))
            return 2

    async with lifespan_pool():
        await run_migrations()
        frane: list[LandslideEvent] = []
        for v in verifiche:
            luogo = await verifiche_eventi_repo.upsert(v)
            log.info("registra_verifica.registrata", slug=v.slug, esito=v.esito)
            if v.hazard is not HazardType.LANDSLIDE:
                continue
            if luogo is None:
                log.warning("registra_verifica.frana_senza_punto", slug=v.slug)
                continue
            frane.append(frana_da_verifica(v, *luogo))
        await landslide_upsert(frane)
        totali = await verifiche_eventi_repo.count_by_esito()
    log.info("registra_verifica.done", registrate=len(verifiche), frane=len(frane), **totali)
    return 0
