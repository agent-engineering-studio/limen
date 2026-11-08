"""Capitolo 8, figura «costi»: quanto costerebbe all'anno tenere Limen acceso.

Disegna barre orizzontali con l'intervallo di costo annuo (in migliaia di
dollari USA) dei cinque scenari di `docs/analisi-costi-cloud.md` (redatta il
2026-10-11, prezzi di listino AWS/Azure/GCP nelle regioni italiane), più il
tetto annuo della spesa per Claude (10 $ al mese, `LLM__ANTHROPIC_BUDGET_MENSILE_USD`
in `src/limen/config/settings.py`).

Il costo del server dedicato su cui Limen gira oggi non è documentato nel
repository (sezione «Dati mancanti» del documento): per questo non c'è una
barra «oggi».

Intervalli: minimo e massimo fra i tre provider, dalle tabelle del §3.
Scenario B in alta affidabilità: 700-860 $/mese × 12.

Uscita: docs/book/figure/cap08/costi-stimati.svg
Uso: uv run --no-project --with matplotlib python -I scripts/libro/cap08_costi.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RADICE = Path(__file__).resolve().parents[2]
USCITA = RADICE / "docs/book/figure/cap08/costi-stimati.svg"

# (etichetta, minimo k$, massimo k$, colore)
VOCI = [
    ("Tetto della spesa per l'AI in cloud (Claude)", 0.12, 0.12, "#c9821b"),
    ("A · un solo server in cloud, come quello di oggi", 3.9, 4.4, "#2a6f77"),
    ("B · server + database gestito dal provider", 5.4, 6.3, "#2a6f77"),
    ("C1 · come B + modelli AI a consumo", 5.5, 6.5, "#2a6f77"),
    ("B · con database duplicato (alta affidabilità)", 8.4, 10.3, "#2a6f77"),
    ("C2 · come B + un server con scheda grafica", 11.3, 12.0, "#2a6f77"),
]


def main() -> None:
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"], "svg.fonttype": "none"})
    fig, ax = plt.subplots(figsize=(10, 4.6), facecolor="white")
    ax.set_facecolor("white")
    n = len(VOCI)
    for i, (et, lo, hi, col) in enumerate(VOCI):
        y = n - 1 - i
        larghezza = max(hi - lo, 0.0)
        ax.barh(y, hi, color=col, alpha=0.25, height=0.55)
        ax.barh(y, larghezza if larghezza else 0.08, left=lo, color=col, height=0.55)
        testo = (f"{lo:.1f}–{hi:.1f} k$".replace(".", ",")) if hi != lo else "120 $"
        ax.text(hi + 0.2, y, testo, va="center", fontsize=10)
    ax.set_yticks(range(n))
    ax.set_yticklabels([v[0] for v in reversed(VOCI)], fontsize=10)
    ax.set_xlabel("Costo all'anno, migliaia di dollari USA (listino, ottobre 2026)", fontsize=10)
    ax.set_xlim(0, 14)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#eeeeee", zorder=0)
    ax.set_axisbelow(True)
    fig.suptitle(
        "Il costo vero è il server: l'AI in cloud pesa al massimo 120 $ l'anno",
        fontsize=12.5,
        fontweight="bold",
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        0.015,
        "Parte scura = intervallo fra AWS, Azure e Google Cloud. Il costo del server "
        "dedicato di oggi non è documentato.  Fonte: docs/analisi-costi-cloud.md (2026-10-11).",
        fontsize=8.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    USCITA.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(USCITA, format="svg", facecolor="white")


if __name__ == "__main__":
    main()
