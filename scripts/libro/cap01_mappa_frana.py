"""Capitolo 1 — come appare la mappa: il pericolo frana su tutta Italia.

Cosa disegna: ogni cella da 1 km² colorata con la sua classe di pericolo
frana nell'ultimo calcolo orario, con la stessa scala della mappa di Limen
(frontend/src/lib/risk-colors.ts: RISK_CLASSES e COLORE_IGNOTO per «non
misurato») sullo stesso fondo scuro.

Dati: tabella `latest_risk` (pericolo `landslide`) e centroidi di
`grid_cells`, in sola lettura. Istantanea dell'8 novembre 2026, calcolo
delle 09:13-09:14 UTC. Rilanciando lo script si ottiene l'ultimo calcolo.

Scrive: docs/book/figure/cap01/mappa-frana.png (raster: 312.550 punti in un
SVG peserebbero decine di megabyte).

    uv run --no-project --with matplotlib --with numpy \
        python -I scripts/libro/cap01_mappa_frana.py
"""

from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap01"

# frontend/src/lib/risk-colors.ts
CLASSI = [
    ("None", "Nessuno", "#151c25"),
    ("Low", "Basso", "#134d47"),
    ("Moderate", "Moderato", "#f2d45c"),
    ("High", "Alto", "#f58a30"),
    ("VeryHigh", "Molto alto", "#e33f5a"),
]
IGNOTO = ("ignoto", "Non misurato", "#4f5965")
FONDO = "#0b0f14"

SQL = """
BEGIN READ ONLY;
SELECT round(ST_X(g.centroid)::numeric, 4), round(ST_Y(g.centroid)::numeric, 4),
       CASE WHEN r.measured IS FALSE OR r.class IS NULL THEN 'ignoto' ELSE r.class END,
       to_char(max(r.computed_at) OVER (), 'YYYY-MM-DD HH24:MI')
FROM grid_cells g
LEFT JOIN latest_risk r ON r.cell_id = g.id AND r.hazard_type = 'landslide';
ROLLBACK;
"""


def leggi_db() -> tuple[np.ndarray, np.ndarray, list[str], str]:
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
            "-At",
            "-q",
            "-F",
            "\t",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=SQL,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    righe = [r.split("\t") for r in out.splitlines() if r.count("\t") == 3]
    x = np.array([float(r[0]) for r in righe])
    y = np.array([float(r[1]) for r in righe])
    return x, y, [r[2] for r in righe], righe[0][3]


def main() -> None:
    x, y, classi, quando = leggi_db()
    conta = Counter(classi)
    colori = {c: col for c, _, col in [*CLASSI, IGNOTO]}

    fig, ax = plt.subplots(figsize=(7.2, 8.4), dpi=160)
    fig.patch.set_facecolor(FONDO)
    ax.set_facecolor(FONDO)
    # Le classi alte per ultime, così restano sopra.
    for c, _, _ in [IGNOTO, *CLASSI]:
        m = np.array([k == c for k in classi])
        if m.any():
            ax.scatter(x[m], y[m], s=0.35, marker="s", linewidths=0, c=colori[c])

    ax.set_xlim(6.4, 18.8)
    ax.set_ylim(35.4, 47.2)
    ax.set_aspect(1 / 0.75)
    ax.axis("off")

    voci = [
        Patch(
            facecolor=col,
            edgecolor="#8b949e",
            linewidth=0.4,
            label=f"{nome}: {conta.get(c, 0):,}".replace(",", "."),
        )
        for c, nome, col in [*CLASSI, IGNOTO]
    ]
    leg = ax.legend(
        handles=voci,
        loc="lower left",
        frameon=False,
        fontsize=8,
        title="Classe di pericolo frana\n(numero di celle)",
        title_fontsize=8.5,
        labelcolor="#e6edf3",
        alignment="left",
    )
    leg.get_title().set_color("#e6edf3")
    ax.set_title("Pericolo frana, cella per cella", loc="left", fontsize=12, color="#e6edf3")
    ax.text(
        18.8,
        35.45,
        f"Calcolo orario del {quando} UTC.\nFonte: database di Limen.",
        ha="right",
        va="bottom",
        fontsize=7,
        color="#8b949e",
    )
    fig.tight_layout()
    fig.savefig(OUT / "mappa-frana.png", facecolor=FONDO)
    print(f"scritto {OUT / 'mappa-frana.png'}: {dict(conta)} alle {quando}")


if __name__ == "__main__":
    main()
