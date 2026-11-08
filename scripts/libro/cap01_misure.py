"""Capitolo 1 — a che punto siamo: eventi presi contro allarmi «comunque».

Cosa disegna: per ogni misura, due barre. La prima è la quota di eventi veri
che la classe di allerta aveva preso prima che accadessero; la seconda è la
quota di celle-giorno (o di celle-ora) in quella classe in un momento
qualunque, cioè quanto spesso il sistema avrebbe acceso l'allerta comunque
(il «tasso di base»). Un sistema utile ha la prima barra lunga e la seconda
corta.

Dati (scritti qui, ognuno con la sua fonte nel repository):
- Incendio, Basilicata 2025 e 2024, perimetri EFFIS, classe alta:
  README.md, sezione «Does it work?» (79 % contro 43 %; 100 % contro 28 %).
- Alluvione, Emilia-Romagna e Lombardia, previsione come fu emessa, aree
  allagate Copernicus EMS, classe alta: backtest dell'8 novembre 2026
  (77 % contro 7,2 %; 80 % contro 7,6 %), come riportato nella guida del libro;
  l'Emilia-Romagna conferma i 77 % / 7,3 % dei commenti di
  src/limen/config/hazards/flood.yaml.
- Frana, Liguria novembre 2019, 131 frane datate e-ITALICA, classe alta:
  issue #122, commento dell'8 ottobre 2026 (10,7 % contro 0,17 % delle
  celle-ora).

Scrive: docs/book/figure/cap01/misure.svg

    uv run --no-project --with matplotlib python -I scripts/libro/cap01_misure.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap01"

MISURE = [
    ("Incendio · Basilicata 2024", 100.0, 28.0),
    ("Incendio · Basilicata 2025", 79.0, 43.0),
    ("Alluvione · Emilia-Romagna", 77.0, 7.2),
    ("Alluvione · Lombardia", 80.0, 7.6),
    ("Frana · Liguria, nov. 2019", 10.7, 0.17),
]

PRESI = "#1f6f78"
COMUNQUE = "#b9b8b1"
INK = "#1a1a1a"
INK2 = "#555555"


def pct(v: float) -> str:
    if v % 1 == 0:
        return f"{v:.0f} %"
    return (f"{v:.2f}" if v < 1 else f"{v:.1f}").replace(".", ",") + " %"


def main() -> None:
    fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=100)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    h = 0.36
    for i, (nome, presi, comunque) in enumerate(reversed(MISURE)):
        y = i
        ax.barh(y + h / 2 + 0.02, presi, height=h, color=PRESI)
        ax.barh(y - h / 2 - 0.02, max(comunque, 0.4), height=h, color=COMUNQUE)
        ax.text(presi + 1.2, y + h / 2 + 0.02, pct(presi), va="center", fontsize=9, color=INK)
        ax.text(max(comunque, 0.4) + 1.2, y - h / 2 - 0.02, pct(comunque), va="center",
                fontsize=9, color=INK2)
    ax.set_yticks(range(len(MISURE)), [m[0] for m in reversed(MISURE)], fontsize=9.5, color=INK)
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 25, 50, 75, 100], ["0 %", "25 %", "50 %", "75 %", "100 %"],
                  fontsize=8.5, color=INK2)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="x", color="#e6e5e0", linewidth=0.8)
    ax.set_axisbelow(True)
    for lato in ("top", "right", "left"):
        ax.spines[lato].set_visible(False)
    ax.spines["bottom"].set_color("#cfcec8")

    fig.text(0.01, 0.965, "Quanti eventi veri prende la classe alta,\n"
             "e quanto spesso si accende comunque", fontsize=11.5, color=INK, va="top")
    ax.text(0, 1.035, "■", transform=ax.transAxes, color=PRESI, fontsize=11, va="bottom")
    ax.text(0.025, 1.035, "eventi veri presi in anticipo", transform=ax.transAxes,
            color=INK, fontsize=9, va="bottom")
    ax.text(0.33, 1.035, "■", transform=ax.transAxes, color=COMUNQUE, fontsize=11, va="bottom")
    ax.text(0.355, 1.035, "momenti qualunque con l'allerta accesa (tasso di base)",
            transform=ax.transAxes, color=INK, fontsize=9, va="bottom")
    fig.text(0.01, 0.01,
             "Fonti: README di Limen (incendio); backtest alluvione dell'8/11/2026; "
             "issue #122, 8/10/2026 (frana).",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 0.86))
    fig.savefig(OUT / "misure.svg", facecolor="white")
    print(f"scritto {OUT / 'misure.svg'}")


if __name__ == "__main__":
    main()
