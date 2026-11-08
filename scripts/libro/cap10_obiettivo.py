"""Capitolo 10, figura «obiettivo»: dove sono le misure di Limen rispetto
all'obiettivo dell'epic #345 (prendere il 90 % degli eventi con al massimo il
10 % di allerte).

Asse orizzontale: quanta parte del territorio-giorno era in allerta (il
«carico»). Asse verticale: quanta parte degli eventi veri era già in allerta
prima. Il riquadro verde è l'obiettivo.

ATTENZIONE: le misure non usano tutte la stessa unità. L'obiettivo è in
comuni-giorno; le misure dell'alluvione sono in celle-giorno, quelle
dell'incendio in giorni sull'AOI, quella della frana in celle. La figura dà un
ordine di grandezza, non un confronto esatto; il testo del capitolo lo dice.

Dati:
- alluvione Emilia-Romagna 77 % / 7,2 %, Lombardia 80 % / 7,6 %: backtest del
  2026-11-08, sola pioggia, previsione come fu emessa (guida comune del libro);
- incendio Basilicata 2025 79 % / 43 %, 2024 100 % / 28 %: README, sezione
  «Does it work?», e CLAUDE.md (backtest-wildfire su perimetri EFFIS);
- frana: «con il 5 % delle celle in allerta si coglie l'11 % delle frane di
  taratura» (backtest della #243, citato nell'epic #345).

Uscita: docs/book/figure/cap10/obiettivo-345.svg
Uso: uv run --no-project --with matplotlib python -I scripts/libro/cap10_obiettivo.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

RADICE = Path(__file__).resolve().parents[2]
USCITA = RADICE / "docs/book/figure/cap10/obiettivo-345.svg"

# (etichetta, carico %, eventi presi %, colore, marcatore)
PUNTI = [
    ("Alluvione, Emilia-Romagna", 7.2, 77, "#2a6f77", "o"),
    ("Alluvione, Lombardia", 7.6, 80, "#2a6f77", "o"),
    ("Incendio, Basilicata 2025", 43, 79, "#c9821b", "s"),
    ("Incendio, Basilicata 2024", 28, 100, "#c9821b", "s"),
    ("Frana, taratura nazionale", 5, 11, "#7a5195", "^"),
]
SPOSTA = {  # posizione delle etichette, in punti
    "Alluvione, Emilia-Romagna": (10, -14),
    "Alluvione, Lombardia": (10, 6),
    "Incendio, Basilicata 2025": (-150, -20),
    "Incendio, Basilicata 2024": (10, -4),
    "Frana, taratura nazionale": (10, -4),
}


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
            "svg.fonttype": "none",
        }
    )
    fig, ax = plt.subplots(figsize=(9, 5.6), facecolor="white")
    ax.set_facecolor("white")
    ax.add_patch(Rectangle((0, 90), 10, 12, color="#4c9a2a", alpha=0.18, lw=0))
    ax.text(0.6, 95, "obiettivo", fontsize=10, color="#2f6b18", fontweight="bold")
    for et, x, y, col, mk in PUNTI:
        ax.scatter(x, y, s=110, color=col, marker=mk, zorder=3)
        ax.annotate(et, (x, y), xytext=SPOSTA[et], textcoords="offset points", fontsize=9.5)
    ax.set_xlim(0, 50)
    ax.set_ylim(0, 105)
    ax.set_xlabel(
        "Quanta parte del territorio era in allerta, % dei giorni (meno è meglio)", fontsize=10
    )
    ax.set_ylabel("Eventi veri già in allerta prima, % (più è meglio)", fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(color="#eeeeee")
    ax.set_axisbelow(True)
    fig.suptitle(
        "Alluvione vicina all'obiettivo; incendio: prende molto ma allerta spesso;\nfrana: prende ancora poco",
        fontsize=12,
        fontweight="bold",
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        0.012,
        "Unità non identiche (celle-giorno, giorni, comuni-giorno): un ordine di grandezza.  "
        "Fonti: issue #345, README, backtest alluvione del 2026-11-08.",
        fontsize=8.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.91))
    USCITA.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(USCITA, format="svg", facecolor="white")


if __name__ == "__main__":
    main()
