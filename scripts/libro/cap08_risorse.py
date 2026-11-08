"""Capitolo 8, figura «risorse»: quanto spazio su disco e quanta memoria usa
un'installazione nazionale di Limen (tutte le 20 regioni, 312.550 celle).

Dati (misurati sul server di produzione, non ricalcolati qui):
- `docs/analisi-costi-cloud.md`, §1 «Footprint misurato» (2026-10-11):
  database 39 GB, dati statici ~47 GB, Open-Meteo 8,6 GB, database GeoServer
  4,5 GB; memoria in uso ~10 GB (Postgres 6,3 · GeoServer 1,6 · Open-Meteo 0,9
  · worker 0,7 · MCP 0,4). Dimensionamento consigliato 8 vCPU / 32 GB / ~300 GB.
- issue #308 (2026-10-20): archivio radar per i backtest ~51 GB.
I modelli linguistici locali (423 GB il 2026-10-11, quasi tutti di un modello
poi rimosso il 2026-10-28) sono esclusi: non servono alla mappa.

Uscita: docs/book/figure/cap08/risorse-installazione.svg
Uso: uv run --no-project --with matplotlib python -I scripts/libro/cap08_risorse.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RADICE = Path(__file__).resolve().parents[2]
USCITA = RADICE / "docs/book/figure/cap08/risorse-installazione.svg"

DISCO = [  # (voce, GB, serve alla mappa?)
    ("Dati del territorio (rilievo, suolo, rocce)", 47.0, True),
    ("Database dei punteggi e della storia", 39.0, True),
    ("Archivio meteo in casa (Open-Meteo)", 8.6, True),
    ("Mappe ISPRA per GeoServer (facoltativo)", 4.5, True),
    ("Archivio radar, solo per le misure", 51.0, False),
]
MEMORIA = [
    ("Database", 6.3),
    ("GeoServer (facoltativo)", 1.6),
    ("Meteo in casa", 0.9),
    ("Calcolo orario", 0.7),
    ("Strumenti per agenti AI", 0.4),
]
PETROLIO, GRIGIO = "#2a6f77", "#9aa5a8"


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
            "svg.fonttype": "none",
        }
    )
    fig, (a1, a2) = plt.subplots(
        1, 2, figsize=(11, 4.4), facecolor="white", gridspec_kw={"width_ratios": [1.35, 1]}
    )
    for ax in (a1, a2):
        ax.set_facecolor("white")
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#eeeeee")
        ax.set_axisbelow(True)

    n = len(DISCO)
    for i, (_voce, gb, mappa) in enumerate(DISCO):
        y = n - 1 - i
        a1.barh(y, gb, color=PETROLIO if mappa else GRIGIO, height=0.6)
        a1.text(gb + 1, y, f"{gb:g} GB".replace(".", ","), va="center", fontsize=10)
    a1.set_yticks(range(n))
    a1.set_yticklabels([d[0] for d in reversed(DISCO)], fontsize=9.5)
    a1.set_xlim(0, 62)
    a1.set_xlabel("Spazio su disco, GB", fontsize=10)
    a1.set_title("Disco: circa 100 GB per la mappa", fontsize=11, loc="left")

    m = len(MEMORIA)
    for i, (_voce, gb) in enumerate(MEMORIA):
        y = m - 1 - i
        a2.barh(y, gb, color=PETROLIO, height=0.6)
        a2.text(gb + 0.1, y, f"{gb:g} GB".replace(".", ","), va="center", fontsize=10)
    a2.set_yticks(range(m))
    a2.set_yticklabels([d[0] for d in reversed(MEMORIA)], fontsize=9.5)
    a2.set_xlim(0, 8)
    a2.set_xlabel("Memoria in uso, GB", fontsize=10)
    a2.set_title("Memoria: circa 10 GB", fontsize=11, loc="left")

    fig.suptitle(
        "Tutta Italia sta su un solo server: 8 processori, 32 GB di memoria, 300 GB di disco",
        fontsize=12.5,
        fontweight="bold",
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        0.015,
        "Grigio = non serve alla mappa. Fonte: docs/analisi-costi-cloud.md (misura del "
        "2026-10-11) e issue #308 (archivio radar).",
        fontsize=8.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    USCITA.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(USCITA, format="svg", facecolor="white")


if __name__ == "__main__":
    main()
