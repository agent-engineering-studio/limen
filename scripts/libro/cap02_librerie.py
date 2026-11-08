"""Capitolo 2 — le undici librerie, le fonti che leggono e i pericoli che servono.

Cosa disegna: una tabella visiva. Una riga per libreria, con la fonte dei dati
che legge; tre colonne, una per pericolo. Il segno dice come il dato entra in
Limen: pieno = cambia il colore della mappa; vuoto = serve a misurare se il
motore funziona (verifica, backtest); rombo = alimenta solo il modello di
machine learning in prova.

Dati: il capitolo 2 del libro e la sezione «The companion libraries» del
README, controllati sul codice che le usa (src/limen/integrations/*,
src/limen/core/scoring/caine.py, src/limen/cli/backtest_*.py). Stato all'8
novembre 2026.

Scrive: docs/book/figure/cap02/librerie-fonti-pericoli.svg

    uv run --no-project --with matplotlib python -I scripts/libro/cap02_librerie.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap02"

MAPPA, MISURA, ML = "mappa", "misura", "ml"

# (libreria, cosa fa in parole, fonte, {pericolo: uso})
RIGHE = [
    ("fwi-chain", "indice meteo degli incendi", "calcolo sul meteo (Open-Meteo)", {"incendio": MAPPA}),
    ("effis-client", "aree bruciate in Europa", "EFFIS, Copernicus", {"incendio": MISURA}),
    ("firms-client", "fuochi visti dal satellite", "NASA FIRMS", {"frana": MAPPA, "incendio": ML}),
    ("rainfall-thresholds", "pioggia che fa franare", "soglie del CNR-IRPI", {"frana": MAPPA}),
    ("ingv-shakemap", "quanto ha tremato il suolo", "INGV", {"frana": MAPPA}),
    ("egms-client", "terreno che si muove", "EGMS, Copernicus", {"frana": ML}),
    ("ispra-idrogeo", "frane censite, aree allagabili", "ISPRA IdroGEO", {"frana": MAPPA, "alluvione": MAPPA}),
    ("dpc-radar", "pioggia che sta cadendo", "radar della Protezione civile", {"frana": MISURA, "alluvione": MAPPA}),
    ("glofas-ewds", "portata dei fiumi", "GloFAS, Copernicus", {"alluvione": MAPPA, "incendio": MISURA}),
    ("imageserver-export", "suolo impermeabilizzato", "Agenzia Europea dell'Ambiente", {"alluvione": MAPPA}),
    ("copernicus-ems", "dove è arrivata l'acqua", "Copernicus EMS", {"alluvione": MISURA}),
]
PERICOLI = ["frana", "alluvione", "incendio"]
INK, INK2, RIGA = "#1a1a1a", "#5a5a5a", "#efeee9"
COLORE = "#1f6f78"


def segno(ax, x: float, y: float, uso: str) -> None:
    if uso == MAPPA:
        ax.scatter([x], [y], s=150, marker="o", color=COLORE, zorder=3)
    elif uso == MISURA:
        ax.scatter([x], [y], s=150, marker="o", facecolor="white", edgecolor=COLORE,
                   linewidths=2, zorder=3)
    else:
        ax.scatter([x], [y], s=120, marker="D", facecolor="white", edgecolor=COLORE,
                   linewidths=1.6, hatch="////", zorder=3)


def main() -> None:
    n = len(RIGHE)
    fig, ax = plt.subplots(figsize=(9.0, 6.2), dpi=100)
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(-1.6, n + 1.4)
    ax.axis("off")
    xs = {"frana": 7.2, "alluvione": 8.3, "incendio": 9.4}

    ax.text(0, n + 0.6, "Libreria e cosa fa", fontsize=9.5, color=INK2, weight="bold")
    ax.text(4.3, n + 0.6, "Da quale fonte", fontsize=9.5, color=INK2, weight="bold")
    for p, x in xs.items():
        ax.text(x, n + 0.6, p.capitalize(), fontsize=9.5, color=INK2, weight="bold", ha="center")

    for i, (lib, cosa, fonte, usi) in enumerate(RIGHE):
        y = n - 1 - i
        if i % 2 == 0:
            ax.add_patch(plt.Rectangle((-0.1, y - 0.45), 10.2, 0.9, color=RIGA, zorder=0))
        ax.text(0, y + 0.13, lib, fontsize=9.5, color=INK, family="monospace", va="center")
        ax.text(0, y - 0.22, cosa, fontsize=8.5, color=INK2, va="center")
        ax.text(4.3, y, fonte, fontsize=8.8, color=INK, va="center")
        for p, uso in usi.items():
            segno(ax, xs[p], y, uso)

    y = -1.0
    segno(ax, 0.15, y, MAPPA)
    ax.text(0.4, y, "cambia il colore della mappa", fontsize=8.8, color=INK, va="center")
    segno(ax, 3.75, y, MISURA)
    ax.text(4.0, y, "serve a misurare se il motore funziona", fontsize=8.8, color=INK, va="center")
    segno(ax, 7.6, y, ML)
    ax.text(7.85, y, "solo il modello in prova", fontsize=8.8, color=INK, va="center")

    fig.text(0.01, 0.975, "Le undici librerie: quale fonte leggono, a quale pericolo servono",
             fontsize=12, color=INK, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "librerie-fonti-pericoli.svg", facecolor="white")
    print(f"scritto {OUT / 'librerie-fonti-pericoli.svg'}")


if __name__ == "__main__":
    main()
