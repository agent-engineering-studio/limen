"""``limen verifiche-report`` — quanto prima Limen ha visto gli eventi verificati.

Legge il registro ``verifiche_eventi`` (migrazione 074) e riassume, pericolo
per pericolo, la stessa domanda del fact check: il comune dell'evento era
sopra soglia prima che succedesse? È il metro delle alluvioni dalla stampa,
che arrivano con un comune e un'ora e mai con un perimetro: in
``flood_events`` dichiarerebbero allagate centinaia di celle asciutte, qui
contano per quello che sono.

Accanto alla quota di eventi con una previsione ≥ Moderato c'è il suo tasso
di base, la quota di eventi il cui comune era già ≥ Moderato nei giorni di
fondo (da 10 a 4 giorni prima). Senza, un comune che sta in Moderato tutto
l'anno farebbe sembrare previsto ogni evento: a Melito, San Lorenzo e
Roccaforte del Greco, il 10 ottobre 2026, 74-80 ore di «anticipo» erano lo
sfondo. Solo l'esito ``anticipata`` è una previsione sopra lo sfondo.

Env knobs: ``LIMEN_VERIFICHE_DAL`` / ``LIMEN_VERIFICHE_AL`` (ISO; default
tutto il registro).
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.verifiche_eventi_repo import RigaVerifica, elenca

log = get_logger(__name__)

REPORTS_DIR = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
_ALMENO_MODERATO = frozenset({"Moderate", "High", "VeryHigh"})


@dataclass(frozen=True, slots=True)
class Riepilogo:
    hazard: HazardType
    verificati: int
    non_verificabili: int
    anticipate: int
    contemporanee: int
    mancate: int
    #: Eventi con una previsione ≥ Moderato, sopra lo sfondo o no.
    apparenti: int
    #: Eventi il cui comune era già ≥ Moderato nei giorni di fondo.
    fondo_moderato: int
    con_alto: int
    anticipo_mediano_ore: float | None

    @property
    def quota_anticipate(self) -> float | None:
        return self.anticipate / self.verificati if self.verificati else None

    @property
    def quota_apparenti(self) -> float | None:
        return self.apparenti / self.verificati if self.verificati else None

    @property
    def tasso_di_base(self) -> float | None:
        return self.fondo_moderato / self.verificati if self.verificati else None


def riepiloga(righe: list[RigaVerifica]) -> list[Riepilogo]:
    """Un riepilogo per pericolo presente, nell'ordine dell'enum.

    ``non_verificabile`` resta fuori dal denominatore: è un evento in cui
    Limen non aveva il dato, e contarlo come mancato abbasserebbe il metro
    per una ragione che col modello non c'entra.
    """
    out: list[Riepilogo] = []
    for hazard in HazardType:
        tutte = [r for r in righe if r.hazard is hazard]
        if not tutte:
            continue
        valide = [r for r in tutte if r.esito != "non_verificabile"]
        anticipi = [
            r.anticipo_sopra_fondo_ore
            for r in valide
            if r.esito == "anticipata" and r.anticipo_sopra_fondo_ore is not None
        ]
        out.append(
            Riepilogo(
                hazard=hazard,
                verificati=len(valide),
                non_verificabili=len(tutte) - len(valide),
                anticipate=sum(r.esito == "anticipata" for r in valide),
                contemporanee=sum(r.esito == "contemporanea" for r in valide),
                mancate=sum(r.esito == "mancata" for r in valide),
                apparenti=sum(r.anticipo_ore_moderato is not None for r in valide),
                fondo_moderato=sum(r.fondo_classe_max in _ALMENO_MODERATO for r in valide),
                con_alto=sum(r.anticipo_ore_alto is not None for r in valide),
                anticipo_mediano_ore=statistics.median(anticipi) if anticipi else None,
            )
        )
    return out


def _quota(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def _ore(x: int | float | None) -> str:
    return "—" if x is None else f"{x:.0f} h"


def scrivi_report(
    riepiloghi: list[Riepilogo],
    righe: list[RigaVerifica],
    *,
    dal: datetime | None,
    al: datetime | None,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"verifiche_{datetime.now(UTC).date()}.md"
    finestra = f"{dal.date() if dal else 'inizio'} → {al.date() if al else 'oggi'}"
    lines = [
        "# Verifiche — gli eventi della stampa contro le previsioni di Limen",
        "",
        f"Finestra: **{finestra}** · generato {datetime.now(UTC).isoformat(timespec='minutes')}",
        "",
        "Celle da 1 km², previsione al comune; «≥ Moderato» non è un'allerta "
        "(quella è della Protezione Civile). I numeri piccoli sono aneddoti, non statistica.",
        "",
    ]
    for s in riepiloghi:
        lines += [
            f"## {s.hazard.value}",
            "",
            f"- Eventi verificati: **{s.verificati}** "
            f"(più {s.non_verificabili} non verificabili, fuori dal conto)",
            f"- Anticipate (sopra lo sfondo, ≥ 6 h): **{s.anticipate}** "
            f"({_quota(s.quota_anticipate)}) — contemporanee {s.contemporanee}, "
            f"mancate {s.mancate}",
            f"- Con una previsione ≥ Moderato: {s.apparenti} ({_quota(s.quota_apparenti)}) "
            f"contro un tasso di base di {_quota(s.tasso_di_base)} "
            f"(comune già ≥ Moderato da 10 a 4 giorni prima)",
            f"- Con una previsione ≥ Alto: {s.con_alto}",
            f"- Anticipo mediano delle anticipate: {_ore(s.anticipo_mediano_ore)}",
            "",
            "| Evento | Esito | ≥ Moderato | ≥ Alto | Prevista max | Fondo max |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {r.evento_at.date()} {r.luogo} | {r.esito} | {_ore(r.anticipo_ore_moderato)} "
            f"| {_ore(r.anticipo_ore_alto)} | {r.classe_prevista_max or '—'} "
            f"| {r.fondo_classe_max or '—'} |"
            for r in righe
            if r.hazard is s.hazard
        ]
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def _parse_dt(env_name: str) -> datetime | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def run() -> int:
    dal = _parse_dt("LIMEN_VERIFICHE_DAL")
    al = _parse_dt("LIMEN_VERIFICHE_AL")
    async with lifespan_pool():
        await run_migrations()
        righe = await elenca(dal=dal, al=al)
    riepiloghi = riepiloga(righe)
    if not riepiloghi:
        log.warning("verifiche_report.vuoto", dal=dal, al=al)
        return 0
    path = scrivi_report(riepiloghi, righe, dal=dal, al=al)
    for s in riepiloghi:
        log.info(
            "verifiche_report.hazard",
            hazard=s.hazard.value,
            verificati=s.verificati,
            anticipate=s.anticipate,
            quota_apparenti=s.quota_apparenti,
            tasso_di_base=s.tasso_di_base,
        )
    log.info("verifiche_report.done", report=str(path), eventi=len(righe))
    return 0
