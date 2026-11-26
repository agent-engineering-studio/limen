"""``limen misura-coltivi`` — i roghi agricoli anticipano gli incendi? In sola lettura (#714).

    limen misura-coltivi --regioni it-lombardia,it-piemonte --stima-fino 2023-12-31 \\
        --verifica 2024-2026

Al Nord l'indice meteo a «moderato» prende in Lombardia un incendio su cinque,
e la #714 chiede se i roghi agricoli siano il segnale che manca. La quota di
coltivo sotto i fuochi di una cella (``crop_burning_share``) si ricalcola qui
in memoria con i soli fuochi VIIRS fino a ``--stima-fino``: la colonna del
bootstrap conta fino a oggi, e una cella bruciata nel periodo di verifica
avrebbe la quota proprio per quell'incendio. La verità sono le celle coperte da
perimetri EFFIS del periodo di verifica.

Il report dice tre cose:

* quante celle bruciate avevano già un fuoco, cioè una quota: le altre la
  feature non le può vedere;
* l'AUC stratificata (nodo 0,25° e fascia di quota) della quota e, per
  confronto, dei giorni-incendio passati della stessa cella;
* la quota a parità di giorni-incendio, e regione per regione.

Il report va in ``LIMEN_REPORTS_DIR`` (default ``reports/``). Non scrive nel
database.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from limen.cli import provenienza
from limen.cli.misura import FASCE_QUOTA, PASSO_NODO, anni
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.repos import misure_repo
from limen.integrations.firms import celle
from limen.integrations.firms.worldcover import worldcover_locale
from limen.ml.misure import (
    Campione,
    auc,
    auc_stratificata,
    osservate_attese,
    soglie_quantili,
    strato,
)

log = get_logger(__name__)

NORD = (
    "it-lombardia",
    "it-piemonte",
    "it-veneto",
    "it-emilia-romagna",
    "it-liguria",
    "it-friuli-venezia-giulia",
    "it-trentino-alto-adige",
    "it-valle-d-aosta",
)
#: Come ``limen misura`` per l'incendio: un quarto della cella (#419).
COPERTURA = 0.25
#: Il confine fra «poche volte» e «spesso» per la quota a parità di fuoco.
SPESSO = 3


@dataclass(frozen=True, slots=True)
class Cella:
    regione: str
    lon: float
    lat: float
    quota: float | None
    giorni: int
    coltivo: float | None
    bruciata: bool


@dataclass(frozen=True, slots=True)
class Regione:
    nome: str
    celle: int
    bruciate: int
    con_fuoco: list[Cella]


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = top.add_parser(
        "misura-coltivi",
        help="la quota di coltivo sotto i fuochi anticipa gli incendi? (sola lettura, #714)",
    )
    p.add_argument("--regioni", default=",".join(NORD), help="AOI separate da virgola")
    p.add_argument(
        "--stima-fino", default="2023-12-31", help="ultimo giorno dei fuochi che fanno la quota"
    )
    p.add_argument("--verifica", default="2024-2026", help="anni della verità EFFIS")
    p.add_argument("--copertura", type=float, default=COPERTURA)


def _campione(righe: Sequence[Cella], valore: Callable[[Cella], float | None]) -> Campione:
    tenute = [c for c in righe if valore(c) is not None]
    return Campione(
        valori=np.array([valore(c) for c in tenute], dtype=float),
        positive=np.array([c.bruciata for c in tenute], dtype=bool),
        strati=np.array(
            [strato(c.lon, c.lat, c.quota, passo=PASSO_NODO, fasce=FASCE_QUOTA) for c in tenute]
        ),
    )


def _f(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}"


def _auc(righe: Sequence[Cella]) -> float | None:
    tenute = [c for c in righe if c.coltivo is not None]
    return auc(
        np.array([c.coltivo for c in tenute], dtype=float),
        np.array([c.bruciata for c in tenute], dtype=bool),
    )


def _oa(c: Campione) -> list[str]:
    out = ["| classe | celle | bruciate | attese | O/A |", "|---|---:|---:|---:|---:|"]
    for r in osservate_attese(c, soglie_quantili(c.valori, 5)):
        if not r.celle:
            continue
        rapporto = "—" if r.rapporto is None else f"{r.rapporto:.2f}"
        out.append(f"| {r.classe} | {r.celle} | {r.osservate} | {r.attese:.1f} | {rapporto} |")
    return out


def report(regioni: Sequence[Regione], *, stima_fino: date, verifica: tuple[date, date]) -> str:
    """Il testo del report: puro, dalle celle già lette."""
    tutte = [c for r in regioni for c in r.con_fuoco]
    n_celle = sum(r.celle for r in regioni)
    n_bruciate = sum(r.bruciate for r in regioni)
    viste = sum(c.bruciata for c in tutte)
    coltivo = _campione(tutte, lambda c: c.coltivo)
    giorni = _campione(tutte, lambda c: float(c.giorni))
    a_coltivo, s_coltivo = auc_stratificata(coltivo)
    a_giorni, s_giorni = auc_stratificata(giorni)
    base_dentro = viste / len(tutte) if tutte else None
    fuori = n_celle - len(tutte)
    base_fuori = (n_bruciate - viste) / fuori if fuori else None
    bruciate_q = [c.coltivo for c in tutte if c.bruciata and c.coltivo is not None]
    altre_q = [c.coltivo for c in tutte if not c.bruciata and c.coltivo is not None]
    righe = [
        "# I roghi agricoli anticipano gli incendi? `crop_burning_share` (#714)",
        "",
        f"Regioni: {', '.join(r.nome for r in regioni)}. La quota è ricalcolata con i soli fuochi "
        f"VIIRS di vegetazione fino al {stima_fino.isoformat()}; bruciata è una cella coperta "
        f"per almeno un quarto da perimetri EFFIS fra il {verifica[0].isoformat()} e il "
        f"{verifica[1].isoformat()}. Strati: nodo {PASSO_NODO}° e fascia di quota.",
        "",
        "## Chi la quota la può vedere",
        "",
        f"Celle {n_celle}, bruciate {n_bruciate}. Con almeno un giorno-incendio prima: "
        f"{len(tutte)} celle, e fra le bruciate {viste} su {n_bruciate}"
        + (f" ({viste / n_bruciate:.0%})" if n_bruciate else "")
        + ". Le altre non hanno una quota: nessuna feature fatta dai fuochi passati le vede.",
        "",
        f"Tasso di base: {_f(base_dentro)} fra le celle già bruciate, {_f(base_fuori)} fra le "
        "altre.",
        "",
        "## Sulle celle già bruciate",
        "",
        f"- `crop_burning_share`: AUC stratificata {_f(a_coltivo)} su {s_coltivo} strati"
        + (
            " (sotto 0,5: più coltivo, **meno** incendi)"
            if a_coltivo is not None and a_coltivo < 0.5
            else ""
        )
        + ".",
        f"- giorni-incendio passati, per confronto: AUC stratificata {_f(a_giorni)} su "
        f"{s_giorni} strati.",
        f"- mediana della quota: {_f(float(np.median(bruciate_q)) if bruciate_q else None)} "
        f"sulle celle che bruciano, {_f(float(np.median(altre_q)) if altre_q else None)} sulle "
        "altre.",
        "",
        "### Osservate/attese per classe di quota",
        "",
        *_oa(coltivo),
        "",
        "### A parità di fuoco",
        "",
        f"- giorni-incendio 1-{SPESSO - 1}: AUC della quota "
        f"{_f(_auc([c for c in tutte if c.giorni < SPESSO]))}.",
        f"- giorni-incendio {SPESSO} o più: AUC della quota "
        f"{_f(_auc([c for c in tutte if c.giorni >= SPESSO]))}.",
        "",
        "## Regione per regione",
        "",
        "| regione | celle già bruciate | bruciate dopo | AUC della quota |",
        "|---|---:|---:|---:|",
        *(
            f"| {r.nome} | {len(r.con_fuoco)} | {sum(c.bruciata for c in r.con_fuoco)} | "
            f"{_f(_auc(r.con_fuoco))} |"
            for r in regioni
        ),
        "",
        "AUC non stratificata per regione; «—» dove non ci sono celle bruciate. EFFIS mappa gli "
        "incendi da circa 30 ha: la misura non dice niente sui piccoli abbruciamenti.",
    ]
    return "\n".join(righe) + "\n"


async def leggi_regione(
    aoi_id: str, terra: object, *, stima_fino: date, verifica: tuple[date, date], copertura: float
) -> Regione:
    stats = await celle.statistiche(aoi_id, terra, al=stima_fino)
    luoghi = await misure_repo.luoghi(aoi_id)
    bruciate = await misure_repo.bruciate(
        aoi_id, dal=verifica[0], al=verifica[1], copertura=copertura
    )
    con_fuoco = [
        Cella(
            regione=aoi_id,
            lon=luoghi[k].lon,
            lat=luoghi[k].lat,
            quota=luoghi[k].quota,
            giorni=s.fire_days,
            coltivo=s.cropland,
            bruciata=k in bruciate,
        )
        for k, s in stats.items()
        if s.fire_days and k in luoghi
    ]
    return Regione(aoi_id, len(luoghi), len(bruciate & luoghi.keys()), con_fuoco)


async def run(args: argparse.Namespace) -> int:
    try:
        stima_fino = date.fromisoformat(args.stima_fino)
        verifica = anni(args.verifica)
    except ValueError as exc:
        log.error("misura_coltivi.parametri", error=str(exc))
        return 2
    if verifica[0] <= stima_fino:
        log.error("misura_coltivi.parametri", error="la verifica deve iniziare dopo la stima")
        return 2
    if worldcover_locale() is None:
        log.error(
            "misura_coltivi.worldcover", error="tile WorldCover assenti: limen worldcover-sync"
        )
        return 1
    regioni: list[Regione] = []
    async with lifespan_pool():
        for aoi_id in [a.strip() for a in args.regioni.split(",") if a.strip()]:
            terra = worldcover_locale()  # una per regione: si apre e si chiude in `statistiche`
            regioni.append(
                await leggi_regione(
                    aoi_id,
                    terra,
                    stima_fino=stima_fino,
                    verifica=verifica,
                    copertura=args.copertura,
                )
            )
    testo = report(regioni, stima_fino=stima_fino, verifica=verifica)
    cartella = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
    cartella.mkdir(parents=True, exist_ok=True)
    uscita = cartella / f"misura_coltivi_{stima_fino.year}_{verifica[0].year}-{verifica[1].year}.md"
    provenienza.scrivi_report(uscita, testo)
    log.info("misura_coltivi.done", report=str(uscita))
    return 0
