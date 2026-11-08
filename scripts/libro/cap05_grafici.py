"""Capitolo 5 — grafici delle misure: eventi presi contro tasso di base e carico.

Cosa disegna (in docs/book/figure/cap05/):
  presi_vs_base.svg   quota di eventi presi contro tasso di base, per pericolo,
                      regione e anno: lontano dalla diagonale = il motore distingue
  carico_295.svg      incendio, classe «molto alto»: la tabella di pesi bocciata e
                      la variante E promossa (wildfire-v1.1.0), frecce da oggi alla variante
  carico_420.svg      alluvione, acqua temporanea HRL (#420): le varianti A e B
                      rispetto a oggi, celle allagate prese contro allerte nei giorni qualunque

Da quali dati: numeri trascritti, con la loro fonte accanto a ciascuno, da
  - commenti della issue #295 (backtest-wildfire 2024-25, 2026-11-07);
  - report backtest-wildfire in /Users/gzileni/limen-data/reports/
    (generati 2026-11-07 con wildfire-v1.1.0, classe «molto alto»);
  - commento della issue #420 del 2026-11-08 (backtest-flood, previsione come fu emessa);
  - commenti della issue #122 (backtest frane Liguria nov. 2019, 7-8 ottobre 2026);
  - CLAUDE.md, riga «Fase 2a-2b wildfire» (Basilicata 2024 e 2025).
Nessun accesso al database o alla rete: le misure costano ore di replica e
quote di API, e qui si ridisegnano soltanto.

Esecuzione, dalla radice del repository:
  uv run --no-project --with matplotlib --with numpy python -I scripts/libro/cap05_grafici.py
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RADICE = Path(__file__).resolve().parents[2]
OUT = RADICE / "docs" / "book" / "figure" / "cap05"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "svg.fonttype": "none",
    }
)

COL = {"incendio": "#c0392b", "alluvione": "#1f618d", "frana": "#7e5109", "ipotesi": "#566573"}


def salva(fig, nome: str) -> None:
    fig.savefig(OUT / nome, bbox_inches="tight")
    if anteprima := os.environ.get("LIBRO_ANTEPRIMA"):
        fig.savefig(Path(anteprima) / nome.replace(".svg", ".png"), bbox_inches="tight", dpi=80)
    plt.close(fig)
    print("scritto", OUT / nome)


# (etichetta, presi %, tasso di base %, pericolo, marcatore)
PUNTI = [
    # Incendio, classe «alto», wildfire-v1.0.0 — issue #295, backtest del 2026-11-07
    ("Sicilia 2024", 63.6, 31.6, "incendio", "o"),
    ("Puglia 2024", 65.3, 26.1, "incendio", "o"),
    ("Calabria 2024", 55.5, 24.2, "incendio", "o"),
    ("Sicilia 2025", 68.9, 42.5, "incendio", "o"),
    # Incendio, Basilicata — CLAUDE.md
    ("Basilicata 2025", 79.0, 43.0, "incendio", "o"),
    ("Basilicata 2024", 100.0, 28.0, "incendio", "o"),
    # Incendio, «molto alto», wildfire-v1.1.0 — report backtest-wildfire 2026-11-07
    ("Sicilia 2024", 11.36, 4.58, "incendio", "D"),
    ("Sicilia 2025", 8.95, 4.02, "incendio", "D"),
    ("Calabria 2024", 7.42, 2.11, "incendio", "D"),
    ("Calabria 2025", 7.74, 1.86, "incendio", "D"),
    ("Puglia 2025", 4.07, 0.69, "incendio", "D"),
    # Alluvione, «alto», previsione come fu emessa, solo pioggia — issue #420, 2026-11-08
    ("Emilia-Romagna", 76.8, 7.2, "alluvione", "s"),
    ("Lombardia", 79.9, 7.6, "alluvione", "s"),
    ("Sardegna", 86.1, 9.5, "alluvione", "s"),
    # Frana, Liguria novembre 2019 — issue #122
    ("Liguria 2019, «alto»", 10.7, 0.17, "frana", "^"),
    ("Liguria 2019, «moderato»", 90.8, 70.0, "frana", "v"),
]


def figura_presi_vs_base() -> None:
    fig, ax = plt.subplots(figsize=(8.2, 5.6))
    x = np.logspace(-1, 2.1, 200)
    for k, stile, et in [(1, "-", "come il caso"), (3, "--", "3 volte il caso"), (10, ":", "10 volte il caso"),
                         (50, "-.", "50 volte")]:
        ax.plot(x, k * x, color="#999", lw=1, ls=stile)
        xt = 0.55 * 100 / k
        ax.text(xt, k * xt, et, fontsize=7.5, color="#555", ha="center", va="center",
                bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none"})
    ax.plot([100], [100], "X", ms=10, color=COL["ipotesi"])
    ax.annotate("«sempre in allerta»:\nprende tutto, non distingue niente", (100, 100), xytext=(20, 4),
                fontsize=8, color=COL["ipotesi"], arrowprops={"arrowstyle": "->", "color": COL["ipotesi"]})
    etichette = {
        "Basilicata 2024": (-62, 4), "Basilicata 2025": (-30, -14),
        "Liguria 2019, «moderato»": (-40, 9), "Liguria 2019, «alto»": (6, 0),
        "Emilia-Romagna": (-40, -13), "Lombardia": (-52, 0), "Sardegna": (-12, 8),
        "Puglia 2025": (6, -2),
    }
    for et, presi, base, per, mk in PUNTI:
        ax.plot([base], [presi], mk, color=COL[per], ms=7, mec="white", mew=0.6)
        if et in etichette:
            ax.annotate(et, (base, presi), xytext=etichette[et], textcoords="offset points", fontsize=7.5,
                        color="#333")
    ax.annotate("Sicilia, Calabria", (3, 8.5), xytext=(4, 2.2), fontsize=7.5, color="#333",
                arrowprops={"arrowstyle": "-", "color": "#999"})
    ax.annotate("Sicilia, Puglia, Calabria", (30, 62), xytext=(7, 30), fontsize=7.5, color="#333",
                arrowprops={"arrowstyle": "-", "color": "#999"})
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.1, 130)
    ax.set_ylim(0.5, 130)
    tic = [0.1, 0.3, 1, 3, 10, 30, 100]
    lab = ["0,1", "0,3", "1", "3", "10", "30", "100"]
    ax.set_xticks(tic, lab)
    ax.set_yticks([1, 3, 10, 30, 100], ["1", "3", "10", "30", "100"])
    ax.set_xlabel("quanto spesso Limen è in allerta comunque (tasso di base, %)")
    ax.set_ylabel("eventi veri presi in tempo (%)")
    leg = [
        plt.Line2D([], [], marker="o", ls="", color=COL["incendio"], label="incendio, «alto»"),
        plt.Line2D([], [], marker="D", ls="", color=COL["incendio"], label="incendio, «molto alto»"),
        plt.Line2D([], [], marker="s", ls="", color=COL["alluvione"], label="alluvione, «alto»"),
        plt.Line2D([], [], marker="^", ls="", color=COL["frana"], label="frana, «alto»"),
        plt.Line2D([], [], marker="v", ls="", color=COL["frana"], label="frana, «moderato»"),
    ]
    ax.legend(handles=leg, frameon=False, fontsize=8, loc="upper left")
    ax.set_title("Quanti eventi presi, e a quale prezzo:\npiù il punto sta sopra la diagonale, più il motore distingue",
                 loc="left", fontsize=10)
    salva(fig, "presi_vs_base.svg")


def frecce(ax, righe, colore):
    for et, c0, c1, h0, h1 in righe:
        ax.annotate("", (c1, h1), (c0, h0), arrowprops={"arrowstyle": "->", "color": colore, "lw": 1.6})
        ax.plot([c0], [h0], "o", color="#888", ms=5)
        ax.annotate(et, (c0, h0), xytext=(-4, 5), textcoords="offset points", fontsize=7.5, ha="right", color="#333")


def figura_carico_295() -> None:
    # (etichetta, carico oggi, carico variante, presi oggi, presi variante) — issue #295
    bocciata = [
        ("Sicilia 2024", 1.8, 0.6, 8.0, 3.5),
        ("Calabria 2024", 1.3, 0.3, 7.4, 1.3),
        ("Sicilia 2025", 1.9, 0.6, 6.2, 2.9),
        ("Puglia 2024", 0.3, 0.0, 0.0, 0.8),
    ]
    promossa = [
        ("Sicilia 2024", 1.8, 2.3, 8.0, 11.4),
        ("Calabria 2024", 1.31, 1.46, 7.4, 7.4),
        ("Sicilia 2025", 1.9, 2.4, 6.2, 9.0),
        ("Puglia 2024", 0.33, 0.37, 0.0, 0.8),
        ("Puglia 2025", 0.57, 0.65, 3.1, 4.1),
        ("Calabria 2025", 2.19, 2.41, 7.6, 7.7),
    ]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    frecce(a1, bocciata, "#a93226")
    a1.set_title("Pesi stimati per tutte le coperture:\nil rosso si svuota (bocciata)", loc="left", fontsize=10)
    frecce(a2, promossa, "#117864")
    a2.set_title("Variante E, solo praterie e vegetazione rada:\npiù incendi presi, poco carico in più (promossa)",
                 loc="left", fontsize=10)
    for ax in (a1, a2):
        ax.set_xlim(-0.1, 2.7)
        ax.set_ylim(-0.5, 12.5)
        ax.set_xlabel("territorio in «molto alto» (% delle giornate-cella)")
    a1.set_ylabel("incendi presi in «molto alto» (%)")
    fig.suptitle("Incendio, classe «molto alto», estati 2024 e 2025: da oggi (punto grigio) alla variante (freccia)",
                 x=0.01, ha="left", fontsize=10.5, y=1.04)
    salva(fig, "carico_295.svg")


def figura_carico_420() -> None:
    # (regione, celle allagate, (carico, prese) oggi, A, B) — issue #420, 2026-11-08
    dati = [
        ("Emilia-Romagna", 1175, (7.2, 902), (8.5, 958), (6.7, 884)),
        ("Lombardia", 333, (7.6, 266), (8.7, 281), (7.2, 264)),
        ("Sardegna", 101, (9.5, 87), (11.1, 92), (8.4, 84)),
        ("Molise", 73, (11.4, 69), (12.1, 70), (10.8, 69)),
        ("Puglia", 43, (4.6, 24), (6.1, 25), (4.6, 24)),
    ]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for reg, n, o, a, b in dati:
        po, pa, pb = (100 * v[1] / n for v in (o, a, b))
        ax.annotate("", (a[0], pa), (o[0], po), arrowprops={"arrowstyle": "->", "color": "#b9770e", "lw": 1.6})
        ax.annotate("", (b[0], pb), (o[0], po), arrowprops={"arrowstyle": "->", "color": "#1f618d", "lw": 1.6})
        ax.plot([o[0]], [po], "o", color="#555", ms=6)
        ax.annotate(reg, (o[0], po), xytext=(-6, 6), textcoords="offset points", fontsize=8, ha="right")
    ax.plot([], [], color="#b9770e", lw=1.6, label="A: alza e abbassa le zone mappate")
    ax.plot([], [], color="#1f618d", lw=1.6, label="B: solo verso il basso")
    ax.plot([], [], "o", color="#555", label="oggi (flood-v1.3.0)")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax.set_xlabel("allerte «alto» nei giorni qualunque (% delle celle-giorno)")
    ax.set_ylabel("celle allagate prese in tempo (%)")
    ax.set_title("Alluvione, acqua temporanea dal satellite: A prende di più perché allerta di più,\n"
                 "B allerta di meno ma perde allagamenti veri. Nessuna delle due passa.", loc="left", fontsize=10)
    salva(fig, "carico_420.svg")


if __name__ == "__main__":
    figura_presi_vs_base()
    figura_carico_295()
    figura_carico_420()
