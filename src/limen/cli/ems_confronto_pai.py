"""``limen ems-confronto-pai`` — l'acqua osservata da Copernicus EMS cade nel PAI? (#713)

    limen ems-confronto-pai --attivazioni EMSR659,EMSR664,EMSR705

Per ogni attivazione in ``flood_events``: l'acqua osservata (unione dei
prodotti che non sono di monitoraggio) divisa fra le classi P3/P2/P1 del
mosaico idraulico ISPRA caricato in ``sorgenti`` da ``limen carica-vettori``,
vince la classe più alta, e la parte fuori da ogni zona — grezza e filtrata
(oltre ``--tolleranza-m`` dalle zone, in macchie di almeno
``--patch-minima-ha``). Aree in EPSG:3035.

Solo l'acqua che si è vista: fuori dalla maschera di osservazione nessuno
ha guardato, e quella zona non è asciutta. Le quote quindi dicono quanta
dell'acqua vista stava in una zona PAI, non quanta zona PAI si è allagata.

Misura e basta: non tocca il punteggio, gli YAML né il database (solo
``SELECT``). Il report va in ``LIMEN_REPORTS_DIR`` (default ``reports/``).
Attivazioni anche da ``LIMEN_EMS_PAI_ATTIVAZIONI``; nessuna ⇒ tutte.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from limen.cli import provenienza
from limen.core.ems_pai import (
    CLASSI,
    PATCH_MINIMA_M2,
    TOLLERANZA_M,
    Ripartizione,
    di_monitoraggio,
    prodotto,
    ripartisci,
)
from limen.core.ems_registro import attribuzione
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.repos import flood_events_repo
from limen.integrations.geoserver_source.loader import zone_idrauliche

log = get_logger(__name__)

_ATTIVAZIONI_ENV = "LIMEN_EMS_PAI_ATTIVAZIONI"


@dataclass(frozen=True, slots=True)
class Misura:
    codice: str
    nome: str | None
    anno: int
    prodotti: tuple[str, ...]
    esclusi: tuple[str, ...]
    ripartizione: Ripartizione
    tabelle: dict[str, str]


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = top.add_parser(
        "ems-confronto-pai",
        help="acqua osservata Copernicus EMS per classe idraulica ISPRA (sola lettura, #713)",
    )
    p.add_argument(
        "--attivazioni",
        default=None,
        help=f"codici separati da virgola (default: {_ATTIVAZIONI_ENV}, o tutte)",
    )
    p.add_argument("--tolleranza-m", type=float, default=TOLLERANZA_M)
    p.add_argument("--patch-minima-ha", type=float, default=PATCH_MINIMA_M2 / 10_000)


def _km2(m2: float) -> str:
    return f"{m2 / 1e6:.2f}"


def _pct(r: Ripartizione, m2: float) -> str:
    q = r.quota(m2)
    return "—" if q is None else f"{100 * q:.0f} %"


def report(
    misure: Sequence[Misura],
    *,
    tabelle: dict[str, str],
    tolleranza_m: float,
    patch_minima_ha: float,
) -> str:
    righe = [
        "# Acqua osservata Copernicus EMS e classi idrauliche ISPRA",
        "",
        "Acqua = unione dei prodotti che non sono di monitoraggio (mai la somma dei `MONIT`). "
        "Classi esclusive, vince la più alta. «Fuori filtrato» = acqua oltre "
        f"{tolleranza_m:g} m da ogni zona, in macchie di almeno {patch_minima_ha:g} ha. "
        "Aree in EPSG:3035.",
        "",
        "Mosaico: " + ", ".join(f"{c} `{tabelle[c]}`" for c in CLASSI if c in tabelle) + ".",
        "",
        "| Attivazione | Acqua km² | P3 | P2 | P1 | Fuori grezzo | Fuori filtrato km² | Macchie |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in misure:
        r = m.ripartizione
        righe.append(
            f"| {m.codice} | {_km2(r.acqua_m2)} | "
            + " | ".join(_pct(r, r.per_classe_m2[c]) for c in CLASSI)
            + f" | {_pct(r, r.fuori_m2)} | {_km2(r.fuori_filtrato_m2)} | {r.macchie_fuori} |"
        )
    righe += ["", "## Prodotti", "", "| Attivazione | Nome | Usati | Esclusi (monitoraggio) |"]
    righe.append("|---|---|---|---|")
    for m in misure:
        righe.append(
            f"| {m.codice} | {m.nome or ''} | {' '.join(m.prodotti)} | "
            f"{' '.join(m.esclusi) or '—'} |"
        )
    anni = sorted({m.anno for m in misure})
    righe += [
        "",
        "Una mappa satellitare è un limite inferiore: piene brevi, urbane o sotto chioma "
        "possono non vedersi. Fuori dalla maschera di osservazione nessuno ha guardato. "
        "Non è un servizio di allerta.",
        "",
        *(f"{attribuzione(a)}." for a in anni),
    ]
    return "\n".join(righe) + "\n"


async def misura(
    codice: str, nome: str | None, *, tolleranza_m: float, patch_minima_m2: float
) -> Misura | None:
    righe = await flood_events_repo.acqua_osservata(codice)
    riquadro = await flood_events_repo.riquadro(codice)
    if not righe or riquadro is None:
        log.warning("ems_pai.attivazione_assente", attivazione=codice)
        return None
    zone = await zone_idrauliche(riquadro)
    if zone is None:
        raise RuntimeError("mosaico idraulico ISPRA assente: limen carica-vettori")
    tenute = [r for r in righe if not di_monitoraggio(prodotto(r.id))]
    ripartizione = await asyncio.to_thread(
        ripartisci,
        [r.geom for r in tenute],
        zone.pezzi,
        tolleranza_m=tolleranza_m,
        patch_minima_m2=patch_minima_m2,
    )
    log.info("ems_pai.misura", attivazione=codice, acqua_km2=ripartizione.acqua_m2 / 1e6)
    return Misura(
        codice=codice,
        nome=nome,
        anno=min(r.event_time for r in righe).year,
        prodotti=tuple(sorted({prodotto(r.id) for r in tenute})),
        esclusi=tuple(sorted({prodotto(r.id) for r in righe} - {prodotto(r.id) for r in tenute})),
        ripartizione=ripartizione,
        tabelle=zone.tabelle,
    )


async def run(args: argparse.Namespace) -> int:
    scelte = args.attivazioni or os.getenv(_ATTIVAZIONI_ENV) or ""
    codici = [c.strip().upper() for c in scelte.split(",") if c.strip()]
    patch_m2 = args.patch_minima_ha * 10_000
    misure: list[Misura] = []
    async with lifespan_pool():
        catalogo = {
            a.activation_code: a.name for a in await flood_events_repo.activations_summary()
        }
        for codice in codici or list(catalogo):
            try:
                m = await misura(
                    codice,
                    catalogo.get(codice),
                    tolleranza_m=args.tolleranza_m,
                    patch_minima_m2=patch_m2,
                )
            except RuntimeError as exc:
                log.error("ems_pai.mosaico", error=str(exc))
                return 1
            if m is not None:
                misure.append(m)
    if not misure:
        log.error("ems_pai.vuoto", attivazioni=codici or "tutte")
        return 1
    testo = report(
        misure,
        tabelle=misure[0].tabelle,
        tolleranza_m=args.tolleranza_m,
        patch_minima_ha=args.patch_minima_ha,
    )
    cartella = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
    cartella.mkdir(parents=True, exist_ok=True)
    nome = "_".join(m.codice for m in misure) if len(misure) <= 4 else "tutte"
    uscita = cartella / f"ems_confronto_pai_{nome}.md"
    provenienza.scrivi_report(uscita, testo)
    log.info("ems_pai.done", report=str(uscita))
    return 0
