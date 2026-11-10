"""``limen misura`` — quanto distingue una feature per cella, in sola lettura (#480).

    limen misura --pericolo wildfire --feature fire_density \\
        --stima 2021-2023 --verifica 2024-2026

Per ogni periodo: AUC stratificata per nodo 0,25° e fascia di quota e tabella
osservate/attese per classe della feature, con le classi fissate sul periodo
di stima. Il report va in ``LIMEN_REPORTS_DIR`` (default ``reports/``); nel
log restano le due AUC. Non scrive nel database.
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

import numpy as np

from limen.cli import provenienza
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.data.db import lifespan_pool
from limen.data.repos import misure_repo
from limen.ml.misure import (
    Campione,
    RigaOA,
    auc_stratificata,
    osservate_attese,
    soglie_quantili,
    strato,
)

log = get_logger(__name__)

#: La quota coperta perché una cella sia positiva: un quarto per il bruciato
#: (#419), l'1 % per l'allagato (#420, #469), dove i poligoni EMS sono strisce.
COPERTURA_DEFAULT = {HazardType.WILDFIRE: 0.25, HazardType.FLOOD: 0.01}
PASSO_NODO = 0.25
FASCE_QUOTA = (200.0, 500.0, 1000.0)


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = top.add_parser(
        "misura", help="AUC e osservate/attese di una feature per cella (sola lettura, #480)"
    )
    p.add_argument("--pericolo", required=True, choices=["wildfire", "flood"])
    p.add_argument("--feature", required=True, help="colonna numerica di cell_static_factors")
    p.add_argument("--stima", required=True, help="anni del periodo di stima, es. 2021-2023")
    p.add_argument("--verifica", required=True, help="anni del periodo di verifica, es. 2024-2026")
    p.add_argument("--copertura", type=float, default=None, help="quota coperta per dire positiva")
    p.add_argument("--classi", type=int, default=5, help="classi della feature (quantili)")


def anni(testo: str) -> tuple[date, date]:
    a, _, b = testo.partition("-")
    try:
        inizio, fine = int(a), int(b or a)
    except ValueError as exc:
        raise ValueError(f"anni: {testo!r}, atteso AAAA-AAAA") from exc
    if fine < inizio:
        raise ValueError(f"anni: {testo!r} va all'indietro")
    return date(inizio, 1, 1), date(fine, 12, 31)


def campione(righe: list[misure_repo.CellaMisura]) -> Campione:
    return Campione(
        valori=np.array([r.valore for r in righe], dtype=float),
        positive=np.array([r.positiva for r in righe], dtype=bool),
        strati=np.array(
            [strato(r.lon, r.lat, r.quota, passo=PASSO_NODO, fasce=FASCE_QUOTA) for r in righe]
        ),
    )


def _tabella(righe: list[RigaOA]) -> list[str]:
    out = ["| classe | celle | osservate | attese | O/A |", "|---|---:|---:|---:|---:|"]
    for r in righe:
        rapporto = "—" if r.rapporto is None else f"{r.rapporto:.2f}"
        out.append(f"| {r.classe} | {r.celle} | {r.osservate} | {r.attese:.1f} | {rapporto} |")
    return out


def report(
    *,
    hazard: HazardType,
    feature: str,
    copertura: float,
    periodi: list[tuple[str, Campione]],
    soglie: np.ndarray,
) -> tuple[str, dict[str, float | None]]:
    righe = [
        f"# Misura di `{feature}` per il pericolo {hazard.value}",
        "",
        f"Positiva: cella coperta per almeno {copertura:.0%}. Strati: nodo {PASSO_NODO}° e "
        f"fascia di quota (confini {', '.join(f'{f:g}' for f in FASCE_QUOTA)} m). "
        "Classi fissate sul periodo di stima.",
        "",
    ]
    aucs: dict[str, float | None] = {}
    for nome, c in periodi:
        a, strati = auc_stratificata(c)
        aucs[nome] = a
        righe += [
            f"## {nome}",
            "",
            f"Celle {len(c.valori)}, positive {int(c.positive.sum())}; "
            f"AUC stratificata {'—' if a is None else f'{a:.3f}'} su {strati} strati"
            + (
                f" (sotto 0,5: i valori **bassi** hanno più eventi; 1 - AUC = {1 - a:.3f})."
                if a is not None and a < 0.5
                else "."
            ),
            "",
            *_tabella(osservate_attese(c, soglie)),
            "",
        ]
    return "\n".join(righe), aucs


async def run(args: argparse.Namespace) -> int:
    hazard = HazardType(args.pericolo)
    copertura = args.copertura if args.copertura is not None else COPERTURA_DEFAULT[hazard]
    try:
        periodi_date = [("stima", anni(args.stima)), ("verifica", anni(args.verifica))]
    except ValueError as exc:
        log.error("misura.parametri", error=str(exc))
        return 2
    periodi: list[tuple[str, Campione]] = []
    async with lifespan_pool():
        for nome, (dal, al) in periodi_date:
            try:
                righe = await misure_repo.celle(
                    hazard, args.feature, dal=dal, al=al, copertura=copertura
                )
            except ValueError as exc:
                log.error("misura.parametri", error=str(exc))
                return 2
            if not righe:
                log.error("misura.vuota", periodo=nome, dal=str(dal), al=str(al))
                return 1
            periodi.append((f"{nome} {dal.year}-{al.year}", campione(righe)))
    soglie = soglie_quantili(periodi[0][1].valori, args.classi)
    testo, aucs = report(
        hazard=hazard, feature=args.feature, copertura=copertura, periodi=periodi, soglie=soglie
    )
    cartella = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
    cartella.mkdir(parents=True, exist_ok=True)
    uscita = cartella / f"misura_{hazard.value}_{args.feature}.md"
    provenienza.scrivi_report(uscita, testo)
    log.info("misura.done", report=str(uscita), **{k.split()[0]: v for k, v in aucs.items()})
    return 0
