"""Capitolo 6 — quanto sono bravi gli sfidanti ML, rispetto alla formula e al caso.

Cosa disegna: per frana e incendio, l'area sotto la curva precisione-richiamo
(AUC-PR) misurata con la validazione a blocchi geografici, per tre «concorrenti»:
il caso (la quota di positivi nel campione, che è l'AUC-PR di chi tira a
indovinare), la formula deterministica di Limen (il campione) e il modello
addestrato (lo sfidante). Un solo messaggio: lo sfidante batte la formula, ma
nessuno dei due è vicino a 1.

Dati (non nel database di questa installazione, che non ha né campioni né
registro MLflow: vedi il capitolo). Fonti nel repository:
  * frana — issue #5 (retrain v3 del 2026-07-06): 37.476 campioni, AUC-PR
    0,597 ± 0,042; formula 0,28 (README, tabella «Misure»). Quota di positivi:
    rapporto di campionamento 1:5 (`TrainingSettings.background_ratio=5`),
    cioè circa 1/6 = 0,167.
  * incendio — issue #68 (2026-09-09): 30.066 campioni, 4.814 positivi
    (quota 0,160), gradient boosting 0,352, Random Forest 0,367, logistica
    0,284, formula (solo FWI) 0,237.

    uv run --no-project --with matplotlib python -I scripts/libro/cap06_misure_ml.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap06"

GRIGIO = "#b8b8b8"
FORMULA = "#0072B2"
MODELLO = "#D55E00"

PANNELLI = [
    (
        "Frana (37.476 esempi)",
        [
            ("tirare a indovinare", 1 / 6, GRIGIO),
            ("formula di Limen", 0.28, FORMULA),
            ("modello addestrato", 0.597, MODELLO),
        ],
    ),
    (
        "Incendio (30.066 esempi, una stagione)",
        [
            ("tirare a indovinare", 4814 / 30066, GRIGIO),
            ("formula di Limen (solo meteo)", 0.237, FORMULA),
            ("modello addestrato", 0.352, MODELLO),
        ],
    ),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 4.6), facecolor="white", sharex=True)
    for ax, (titolo, barre) in zip(axes, PANNELLI, strict=True):
        etichette = [b[0] for b in barre][::-1]
        valori = [b[1] for b in barre][::-1]
        colori = [b[2] for b in barre][::-1]
        ax.barh(etichette, valori, color=colori, height=0.62)
        for y, v in enumerate(valori):
            ax.text(v + 0.012, y, f"{v:.2f}".replace(".", ","), va="center", fontsize=9.5)
        ax.set_title(titolo, fontsize=10.5, loc="left")
        ax.set_xlim(0, 1)
        for lato in ("top", "right"):
            ax.spines[lato].set_visible(False)
        ax.tick_params(axis="y", length=0, labelsize=9.5)
    axes[-1].xaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ","))
    )
    axes[-1].set_xlabel(
        "Qualità nel mettere in cima alla lista i casi veri (AUC-PR: 0 = nulla, 1 = perfetto)",
        fontsize=9,
    )
    fig.suptitle(
        "Il modello batte la formula, ma resta lontano dalla perfezione",
        fontsize=12, x=0.01, ha="left",
    )
    fig.tight_layout()
    fig.savefig(OUT / "misure_ml.svg", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
