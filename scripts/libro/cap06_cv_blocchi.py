"""Capitolo 6 — la validazione a blocchi geografici, disegnata sulle celle vere.

Cosa disegna:
  1. `cv_blocchi_italia.svg`: l'Italia divisa in riquadri di 0,5° (circa 50 km)
     e ogni riquadro colorato secondo il gruppo di verifica (fold) a cui lo
     assegna l'algoritmo di Limen: ordinamento, rimescolamento con seme 42,
     assegnazione a turno su 5 gruppi. È lo stesso algoritmo di
     `limen.ml.feature_store.spatial_block_folds` (ricopiato qui per non
     importare il pacchetto), con i parametri di default di `TrainingSettings`
     (`spatial_block_deg=0.5`, `spatial_cv_folds=5`, `seed=42`).
  2. `cv_casuale_vs_blocchi.svg`: un ritaglio fra Toscana, Emilia-Romagna e Umbria, cella per
     cella. A sinistra una divisione casuale (20 % delle celle in verifica,
     sparse fra quelle di addestramento); a destra la divisione a blocchi
     (un gruppo intero in verifica).

Nota onesta: nell'addestramento vero i riquadri sono quelli che contengono
almeno un campione (`training_samples.split_block`); qui sono quelli che
contengono almeno una cella. L'algoritmo è identico, l'assegnazione dei
colori ai singoli riquadri può differire.

Dati: centroidi di `grid_cells` (312.550 celle), database di Limen in sola
lettura (transazione READ ONLY). Misura del 2026-11-08.

    uv run --no-project --with matplotlib --with numpy \
        python -I scripts/libro/cap06_cv_blocchi.py
"""

from __future__ import annotations

import io
import random
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap06"
EDGE = 0.5
K = 5
SEED = 42
# Okabe-Ito: distinguibili anche per chi ha una forma di daltonismo.
COLORI = ["#E69F00", "#56B4E9", "#009E73", "#CC79A7", "#0072B2"]

SQL = """
BEGIN READ ONLY;
COPY (SELECT ST_X(centroid), ST_Y(centroid) FROM grid_cells) TO STDOUT WITH CSV;
ROLLBACK;
"""


def leggi_centroidi() -> np.ndarray:
    out = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "limen-postgres",
            "psql",
            "-U",
            "limen",
            "-d",
            "limen",
            "-q",
            "-At",
        ],
        input=SQL,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    righe = [r for r in out.splitlines() if r and r[0] in "0123456789-"]
    return np.loadtxt(io.StringIO("\n".join(righe)), delimiter=",")


def blocco(lon: float, lat: float) -> str:
    return f"{int(lon // EDGE)}|{int(lat // EDGE)}"


def fold_dei_blocchi(blocchi: list[str]) -> dict[str, int]:
    ordinati = sorted(set(blocchi))
    rng = random.Random(SEED)
    rng.shuffle(ordinati)
    return {b: i % K for i, b in enumerate(ordinati)}


def figura_italia(xy: np.ndarray, folds: dict[str, int]) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 8.2), facecolor="white")
    ax.scatter(xy[:, 0], xy[:, 1], s=0.02, c="#9a9a9a", linewidths=0, rasterized=True)
    for b, f in folds.items():
        x, y = (int(v) for v in b.split("|"))
        ax.add_patch(
            Rectangle(
                (x * EDGE, y * EDGE),
                EDGE,
                EDGE,
                facecolor=COLORI[f],
                edgecolor="white",
                linewidth=0.6,
                alpha=0.78,
            )
        )
    ax.set_xlim(6.4, 18.8)
    ax.set_ylim(35.4, 47.3)
    ax.set_aspect(1 / np.cos(np.radians(41.5)))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(
        "Cinque gruppi di riquadri: a turno, uno fa da esame\n"
        "e gli altri quattro da libro di studio",
        fontsize=12,
        loc="left",
    )
    ax.legend(
        handles=[Patch(color=c, label=f"gruppo {i + 1}") for i, c in enumerate(COLORI)],
        loc="upper right",
        frameon=False,
        fontsize=9,
    )
    ax.text(
        6.5,
        35.6,
        f"{len(folds)} riquadri di circa 50 km di lato, {len(xy):,} celle".replace(",", "."),
        fontsize=8.5,
        color="#444444",
    )
    fig.savefig(OUT / "cv_blocchi_italia.svg", bbox_inches="tight")
    plt.close(fig)


def figura_confronto(xy: np.ndarray, folds: dict[str, int]) -> None:
    lon0, lon1, lat0, lat1 = 10.0, 13.0, 43.0, 44.6
    m = (xy[:, 0] >= lon0) & (xy[:, 0] < lon1) & (xy[:, 1] >= lat0) & (xy[:, 1] < lat1)
    sub = xy[m]
    rng = np.random.default_rng(SEED)
    casuale = rng.random(len(sub)) < 0.2
    gruppo = np.array([folds[blocco(x, y)] for x, y in sub])
    # Il gruppo con più celle nel ritaglio, così la figura mostra un esame vero.
    scelto = np.bincount(gruppo, minlength=K).argmax()
    a_blocchi = gruppo == scelto

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9), facecolor="white")
    for ax, test, titolo in (
        (
            axes[0],
            casuale,
            "Divisione casuale: ogni cella d'esame\nha le vicine nel libro di studio",
        ),
        (
            axes[1],
            a_blocchi,
            "Divisione a blocchi: l'esame è un\nterritorio intero, mai visto prima",
        ),
    ):
        ax.scatter(sub[~test, 0], sub[~test, 1], s=1.2, c="#c9c9c9", linewidths=0, rasterized=True)
        ax.scatter(sub[test, 0], sub[test, 1], s=1.2, c="#D55E00", linewidths=0, rasterized=True)
        ax.set_xlim(lon0, lon1)
        ax.set_ylim(lat0, lat1)
        ax.set_aspect(1 / np.cos(np.radians(43.8)))
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#bbbbbb")
        ax.set_title(titolo, fontsize=10.5, loc="left")
    fig.legend(
        handles=[
            Patch(color="#c9c9c9", label="celle per imparare"),
            Patch(color="#D55E00", label="celle per l'esame"),
        ],
        loc="lower center",
        ncol=2,
        frameon=False,
        fontsize=9,
        bbox_to_anchor=(0.5, -0.04),
    )
    fig.savefig(OUT / "cv_casuale_vs_blocchi.svg", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    xy = leggi_centroidi()
    folds = fold_dei_blocchi([blocco(x, y) for x, y in xy])
    figura_italia(xy, folds)
    figura_confronto(xy, folds)


if __name__ == "__main__":
    main()
