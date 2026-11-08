"""Capitolo 1 — mappa delle venti regioni e del numero di celle per regione.

Cosa disegna: i confini delle aree monitorate (una per regione) con il numero
di celle da 1 km² che Limen calcola in ciascuna, e il totale nazionale.

Dati: tabelle `aoi` e `grid_cells` del database di Limen, in sola lettura
(transazione READ ONLY). Le geometrie sono semplificate in SQL con
ST_SimplifyPreserveTopology (tolleranza 0,01°, circa 1 km) per tenere il
GeoJSON leggero. Misura del 2026-11-08.

Scrive: docs/book/figure/cap01/regioni.geojson e regioni.svg.

    uv run --no-project --with matplotlib --with shapely \
        python -I scripts/libro/cap01_regioni.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
from shapely.geometry import shape

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap01"

SQL = """
BEGIN READ ONLY;
SELECT json_build_object(
  'type', 'FeatureCollection',
  'features', json_agg(f ORDER BY f->'properties'->>'nome')
)
FROM (
  SELECT json_build_object(
    'type', 'Feature',
    'properties', json_build_object('id', a.id, 'nome', a.name, 'celle', c.n),
    'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(a.geom, 0.01), 4)::json
  ) AS f
  FROM aoi a
  JOIN (SELECT aoi_id, count(*) AS n FROM grid_cells GROUP BY aoi_id) c
    ON c.aoi_id = a.id
  WHERE a.kind = 'region'
) s;
ROLLBACK;
"""


def leggi_db() -> dict:
    out = subprocess.run(
        ["docker", "exec", "-i", "limen-postgres", "psql", "-U", "limen", "-d", "limen",
         "-At", "-q", "-v", "ON_ERROR_STOP=1"],
        input=SQL, capture_output=True, text=True, check=True,
    ).stdout
    riga = next(r for r in out.splitlines() if r.startswith("{"))
    return json.loads(riga)


def contorni(geom) -> MplPath:
    vertici, codici = [], []
    poligoni = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for p in poligoni:
        for anello in [p.exterior, *p.interiors]:
            xy = list(anello.coords)
            vertici += xy
            codici += [MplPath.MOVETO] + [MplPath.LINETO] * (len(xy) - 2) + [MplPath.CLOSEPOLY]
    return MplPath(vertici, codici)


# Etichette spostate a mano dove il punto interno cade fuori vista o sopra un'altra.
SPOSTA = {
    "it-valle-d-aosta": (-0.9, 0.35),
    "it-liguria": (-0.2, -0.45),
    "it-molise": (0.25, 0.05),
    "it-umbria": (0.0, -0.05),
    "it-friuli-venezia-giulia": (0.15, 0.1),
    "it-campania": (-0.25, 0.0),
}

NOMI_BREVI = {"it-friuli-venezia-giulia": "Friuli V. G.", "it-trentino-alto-adige": "Trentino-A. A."}


def main() -> None:
    fc = leggi_db()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "regioni.geojson").write_text(json.dumps(fc, ensure_ascii=False))

    totale = sum(f["properties"]["celle"] for f in fc["features"])
    massimo = max(f["properties"]["celle"] for f in fc["features"])
    cmap = plt.get_cmap("cividis")

    fig, ax = plt.subplots(figsize=(7.2, 8.4), dpi=100)
    fig.patch.set_facecolor("white")
    for f in fc["features"]:
        g = shape(f["geometry"])
        n = f["properties"]["celle"]
        colore = cmap(0.25 + 0.7 * n / massimo)
        ax.add_patch(PathPatch(contorni(g), facecolor=colore, edgecolor="white", linewidth=0.8))
        p = g.representative_point()
        dx, dy = SPOSTA.get(f["properties"]["id"], (0.0, 0.0))
        nome = NOMI_BREVI.get(f["properties"]["id"], f["properties"]["nome"])
        ax.text(p.x + dx, p.y + dy, f"{nome}\n{n:,}".replace(",", "."),
                ha="center", va="center", fontsize=6.6, linespacing=1.1, color="#111111",
                path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])

    ax.set_xlim(6.4, 18.8)
    ax.set_ylim(35.4, 47.2)
    ax.set_aspect(1 / 0.75)
    ax.axis("off")
    ax.set_title(
        "Venti regioni, " + f"{totale:,}".replace(",", ".") + " celle da un chilometro quadrato",
        fontsize=12, loc="left", color="#111111",
    )
    ax.text(6.4, 35.55, "Colore più chiaro = più celle (regione più grande).\n"
            "Fonte: database di Limen, 8 novembre 2026.",
            fontsize=7.5, color="#444444", va="bottom")
    fig.tight_layout()
    fig.savefig(OUT / "regioni.svg", facecolor="white")
    print(f"scritto {OUT / 'regioni.svg'} ({totale} celle)")


if __name__ == "__main__":
    main()
