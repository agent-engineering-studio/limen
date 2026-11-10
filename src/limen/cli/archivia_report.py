"""``limen archivia-report`` — un report di misura entra nel repository (#481).

    limen archivia-report reports/backtest_wildfire_it-sicilia_2024-06-01_2024-09-30.md

Copia il report e il suo ``.provenienza.json`` in ``docs/misure`` (``--cartella``)
e riscrive l'indice ``README.md`` da tutti i ``.provenienza.json`` presenti:
data, report, versioni dei motori, commit e comando, il più recente in cima.
Un report senza ``.provenienza.json`` viene da prima della #481 e non si
archivia: rifarlo è il modo di sapere con che cosa è stato misurato.
Rilanciarlo sullo stesso file lo sovrascrive. Non tocca il database.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from limen.cli.provenienza import gemello
from limen.core.logging import get_logger

log = get_logger(__name__)

INDICE = "README.md"
_TESTA = [
    "# Misure di riferimento",
    "",
    "I report di misura che giustificano un cambio di `model_version` o che il libro cita,",
    "con la loro provenienza. Si aggiungono con `limen archivia-report REPORT.md`, che",
    "riscrive questo indice: non modificarlo a mano.",
    "",
    "| generato | report | versioni | commit | comando |",
    "|---|---|---|---|---|",
]


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = top.add_parser(
        "archivia-report", help="copia report di misura e provenienza in docs/misure (#481)"
    )
    p.add_argument("report", nargs="+", help="report .md scritti da un comando di misura")
    p.add_argument("--cartella", default="docs/misure", help="dove archiviarli")


def indice(cartella: Path) -> str:
    voci: list[dict[str, Any]] = [
        json.loads(f.read_text(encoding="utf-8"))
        for f in sorted(cartella.glob("*.provenienza.json"))
    ]
    voci.sort(key=lambda v: (v["generato"], v["report"]), reverse=True)
    righe = list(_TESTA)
    for v in voci:
        versioni = ", ".join(f"`{x}`" for x in v["versioni"].values())
        commit = (v["commit"] or "ignoto")[:12]
        righe.append(
            f"| {v['generato'][:10]} | [{v['report']}]({v['report']}) | {versioni} "
            f"| `{commit}` | `{v['comando']}` |"
        )
    return "\n".join(righe) + "\n"


def run(args: argparse.Namespace) -> int:
    cartella = Path(args.cartella)
    sorgenti = [Path(r) for r in args.report]
    mancanti = [str(r) for r in sorgenti if not r.is_file() or not gemello(r).is_file()]
    if mancanti:
        log.error("archivia_report.senza_provenienza", report=mancanti)
        return 2
    cartella.mkdir(parents=True, exist_ok=True)
    for r in sorgenti:
        shutil.copyfile(r, cartella / r.name)
        shutil.copyfile(gemello(r), gemello(cartella / r.name))
    (cartella / INDICE).write_text(indice(cartella), encoding="utf-8")
    log.info("archivia_report.done", cartella=str(cartella), report=len(sorgenti))
    return 0
