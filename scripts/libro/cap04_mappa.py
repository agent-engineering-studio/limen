"""Capitolo 4 — mappa di esempio: frana e alluvione in Liguria, l'ultima ora calcolata.

Cosa disegna: docs/book/figure/cap04/mappa_liguria.png, due pannelli
(frana sopra, alluvione sotto) con le 5.884 celle da 1 km² della Liguria
colorate per classe con la rampa della mappa di Limen
(frontend/src/lib/risk-colors.ts); in grigio le celle «non misurate»
(colonna measured = false), come sulla mappa pubblica.

Da quali dati: database operativo di Limen, in sola lettura (transazione
READ ONLY), tabelle latest_risk (ultimo punteggio per cella e pericolo),
grid_cells (geometria delle celle) e aoi (confine della regione).
Prima esecuzione: 2026-11-08, punteggi calcolati fra le 09:07 e le 09:13 UTC.
Rieseguendolo si ottiene la mappa dell'ultima ora disponibile.

Esecuzione, dalla radice del repository (serve il container limen-postgres):
  uv run --no-project --with matplotlib --with shapely \
      python -I scripts/libro/cap04_mappa.py
"""

from __future__ import annotations

import csv
import io
import subprocess
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.patches import Patch
from shapely import wkt

RADICE = Path(__file__).resolve().parents[2]
OUT = RADICE / "docs" / "book" / "figure" / "cap04"
AOI = "it-liguria"

RAMPA = {
    "None": "#151c25",
    "Low": "#134d47",
    "Moderate": "#f2d45c",
    "High": "#f58a30",
    "VeryHigh": "#e33f5a",
}
GRIGIO = "#9aa3ad"
ETICHETTE = {
    "None": "nessuno",
    "Low": "basso",
    "Moderate": "moderato",
    "High": "alto",
    "VeryHigh": "molto alto",
}


def sql(query: str) -> list[dict[str, str]]:
    """Esegue una COPY in sola lettura e restituisce le righe come dizionari."""
    comando = (
        "BEGIN READ ONLY; "
        f"COPY ({query}) TO STDOUT WITH CSV HEADER; "
        "ROLLBACK;"
    )
    uscita = subprocess.run(
        ["docker", "exec", "limen-postgres", "psql", "-U", "limen", "-d", "limen",
         "-q", "-v", "ON_ERROR_STOP=1", "-c", comando],
        check=True, capture_output=True, text=True,
    ).stdout
    righe = [r for r in uscita.splitlines() if r not in ("BEGIN", "ROLLBACK")]
    return list(csv.DictReader(io.StringIO("\n".join(righe))))


def main() -> None:
    celle = sql(
        "SELECT l.hazard_type::text AS pericolo, l.class AS classe, "
        "coalesce(l.measured, true) AS misurato, l.computed_at, "
        "ST_AsText(ST_SimplifyPreserveTopology(g.geom, 0.0001)) AS wkt "
        f"FROM latest_risk l JOIN grid_cells g ON g.id = l.cell_id "
        f"WHERE g.aoi_id = '{AOI}' AND l.hazard_type IN ('landslide', 'flood')"
    )
    confine = sql(f"SELECT ST_AsText(ST_Simplify(geom, 0.002)) AS wkt FROM aoi WHERE id = '{AOI}'")[0]["wkt"]
    quando = max(c["computed_at"] for c in celle)[:16]

    fig, assi = plt.subplots(2, 1, figsize=(9, 8.4))
    for ax, (pericolo, titolo) in zip(assi, [("landslide", "Frana"), ("flood", "Alluvione")]):
        ax.margins(0.01)
        sue = [c for c in celle if c["pericolo"] == pericolo]
        poligoni, colori = [], []
        for c in sue:
            geom = wkt.loads(c["wkt"])
            poligoni.append(list(geom.exterior.coords))
            colori.append(RAMPA.get(c["classe"], GRIGIO) if c["misurato"] == "t" else GRIGIO)
        ax.add_collection(PolyCollection(poligoni, facecolors=colori, edgecolors="none", alpha=0.9))
        bordo = wkt.loads(confine)
        for parte in getattr(bordo, "geoms", [bordo]):
            x, y = parte.exterior.xy
            ax.plot(x, y, color="#222", lw=0.6)
        ax.autoscale_view()
        ax.set_aspect(1 / 0.73)  # circa 1/cos(44°): gradi di longitudine più corti
        ax.axis("off")
        conta = Counter(c["classe"] for c in sue if c["misurato"] == "t")
        n = len(sue)
        riga = ", ".join(
            f"{ETICHETTE[k]} {100 * conta[k] / n:.0f} %".replace(".", ",")
            for k in ETICHETTE if conta.get(k)
        )
        ax.set_title(f"{titolo}: {riga}", fontsize=10, loc="left")

    voci = [Patch(color=RAMPA[k], label=ETICHETTE[k]) for k in RAMPA]
    voci.append(Patch(color=GRIGIO, label="non misurato"))
    fig.legend(handles=voci, loc="lower center", ncol=6, frameon=False, fontsize=9)
    fig.subplots_adjust(hspace=0.12, top=0.93, bottom=0.06, left=0.01, right=0.99)
    fig.suptitle(
        f"Liguria, stessa ora, due pericoli (punteggi del {quando[:10]}, ore {quando[11:16]} UTC)",
        x=0.02, ha="left", fontsize=11,
    )
    fig.patch.set_facecolor("white")
    fig.savefig(OUT / "mappa_liguria.png", dpi=160, bbox_inches="tight", facecolor="white")
    print("scritto", OUT / "mappa_liguria.png", "celle", len(celle))


if __name__ == "__main__":
    main()
