"""Figura del capitolo 9 del libro («Cosa manca»).

Disegna ``guadagno-dati-provati.svg``: quanto ha aggiunto ciascun dato nuovo
provato finora, misurato come guadagno di AUC (la capacità di separare i posti
e i giorni dove l'evento è avvenuto da quelli dove non è avvenuto; 0,5 è il
caso, 1 è perfetto), e cosa se n'è deciso.

I numeri non vengono dal database: sono quelli pubblicati nelle issue, letti
il 2026-11-08.

* #282 (frana, umidità del suolo EDO): aggiunta a pioggia e umidità Open-Meteo
  in validazione incrociata per regione, +0,001. NO-GO (2026-10-19).
* #419 (incendio, HRL prati / chioma / conifere): +0,02 di AUC in Italia.
  NO-GO (2026-11-07).
* #420 (alluvione, HRL WaterWetness dentro le aree PAI): AUC 0,61 -> 0,69 in
  Emilia-Romagna e 0,71 -> 0,81 nel resto d'Italia, cioè +0,08 e +0,10; nel
  motore il backtest non passa (2026-11-08).

Uso:
    uv run --no-project --with matplotlib python -I scripts/libro/cap09_misure.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap09"
INK = "#333333"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
                     "svg.fonttype": "none"})

PROVE = [
    ("Frana · umidità del suolo europea (EDO)", 0.001, "scartato: non aggiunge nulla", "#b0b0b0"),
    ("Incendio · prati e chiome a 10 m (Copernicus)", 0.02, "scartato: troppo poco per il costo", "#b0b0b0"),
    ("Alluvione · acqua temporanea, Emilia-Romagna", 0.08, "segnale vero; nel motore il backtest non passa", "#1f6f78"),
    ("Alluvione · acqua temporanea, resto d'Italia", 0.10, "segnale vero; nel motore il backtest non passa", "#1f6f78"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9.0, 3.6))
    y = list(range(len(PROVE)))[::-1]
    for yi, (nome, g, esito, col) in zip(y, PROVE):
        ax.barh(yi, g, color=col, height=0.6)
        ax.text(g + 0.002, yi, (f"+{g:.3f}" if g < 0.01 else f"+{g:.2f}").replace(".", ",") + f"   {esito}",
                va="center", fontsize=9)
    ax.set_yticks(y, [p[0] for p in PROVE])
    ax.set_xlim(0, 0.30)
    ax.set_xticks([0, 0.05, 0.10], ["0", "+0,05", "+0,10"])
    ax.set_xlabel("Quanto il dato migliora la capacità di distinguere dove l'evento è avvenuto (guadagno di AUC)")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color="#dddddd", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_title("Tre dati nuovi, misurati prima di usarli: due scartati, uno promettente",
                 loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "guadagno-dati-provati.svg", facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
