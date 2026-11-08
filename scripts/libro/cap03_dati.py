"""Figure del capitolo 3 del libro («I dati»).

Disegna, dal database operativo di Limen (sola lettura, transazione READ ONLY):

* ``copertura.svg``  — quota delle 312.550 celle che hanno ciascun dato del
  territorio, distinguendo «caricato ovunque», «presente solo dove la fonte ha
  mappato un'area» e «mai calcolato». È la stessa conta di ``limen data-status``
  (``count(colonna)`` su ``grid_cells LEFT JOIN cell_static_factors``), estesa a
  tutte le colonne della tabella.
* ``mappa-pendenza.svg`` — pendenza media di ogni cella da 1 km (DTM 5 m
  CNR-IRPI), su tutta Italia.
* ``mappa-idraulica.svg`` — la classe di pericolosità idraulica ISPRA più grave
  che tocca la cella (P3 alta, P2 media, P1 bassa), su tutta Italia.

Le mappe sono raster da 1 km costruiti dai centroidi delle celle con una
proiezione equirettangolare semplice (sufficiente per una figura), con i
confini regionali semplificati (ST_Simplify 0,01°).

Misura eseguita il 2026-11-08 sull'installazione locale (ultimo aggiornamento
dei fattori statici: 2026-11-07 03:26 UTC).

Uso:
    uv run --no-project --with matplotlib --with numpy --with pandas \
        python -I scripts/libro/cap03_dati.py
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap03"
CONTAINER = "limen-postgres"
INK = "#333333"
MUTED = "#777777"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "svg.fonttype": "none",
    }
)


def psql_copy(sql: str) -> str:
    """Esegue una SELECT in sola lettura e restituisce il CSV."""
    script = f"BEGIN READ ONLY;\nCOPY ({sql}) TO STDOUT WITH CSV HEADER;\nROLLBACK;\n"
    res = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "limen", "-d", "limen", "-q", "-X"],
        input=script,
        capture_output=True,
        text=True,
        check=True,
    )
    return "\n".join(l for l in res.stdout.splitlines() if l not in ("BEGIN", "ROLLBACK"))


# --- 1. copertura ---------------------------------------------------------------

# (etichetta per chi legge, espressione SQL, gruppo)
VOCI = [
    ("Frane già censite vicino (inventario IFFI)", "count(f.iffi_density_500)", "ovunque"),
    ("Pendenza del terreno", "count(f.slope_deg)", "ovunque"),
    ("Copertura del suolo: bosco, campi, città", "count(f.landuse_code)", "ovunque"),
    ("Tipo di roccia (carta geolitologica)", "count(f.litho_weight)", "ovunque"),
    ("Suolo coperto da asfalto e cemento", "count(f.imperviousness_norm)", "ovunque"),
    ("Case accanto al bosco", "count(f.wui_proximity_norm)", "ovunque"),
    ("Distanza dalle strade (OpenStreetMap)", "count(f.distance_to_road_m)", "ovunque"),
    ("Aree a pericolo di frana dei Piani di bacino", "count(f.pai_class_norm)", "aree"),
    ("Aree che possono allagarsi (ISPRA)", "count(f.flood_hazard_norm)", "aree"),
    ("Incendi passati visti dal satellite", "count(*) FILTER (WHERE f.fire_density > 0)", "mai"),
    ("Vicinanza a città e infrastrutture", "count(*) FILTER (WHERE f.near_urban OR f.near_infra)", "mai"),
    ("Umidità del terreno dalla forma del versante", "count(f.twi)", "mai"),
    ("Distanza dalle faglie", "count(f.dist_faults_m)", "mai"),
    ("Popolazione ed edifici", "count(f.population_count)", "mai"),
]


def figura_copertura() -> pd.DataFrame:
    sel = ", ".join(f"{expr} AS c{i}" for i, (_, expr, _) in enumerate(VOCI))
    sql = (
        f"SELECT count(*) AS celle, {sel} FROM grid_cells g "
        "LEFT JOIN cell_static_factors f ON f.cell_id = g.id"
    )
    row = pd.read_csv(io.StringIO(psql_copy(sql))).iloc[0]
    tot = int(row["celle"])
    df = pd.DataFrame(
        {
            "voce": [v[0] for v in VOCI],
            "gruppo": [v[2] for v in VOCI],
            "celle": [int(row[f"c{i}"]) for i in range(len(VOCI))],
        }
    )
    df["pct"] = 100 * df["celle"] / tot
    df.to_csv(OUT / "copertura.csv", index=False)

    colori = {"ovunque": "#1f6f78", "aree": "#e0a526", "mai": "#b0b0b0"}
    fig, ax = plt.subplots(figsize=(9.2, 6.0))
    y = np.arange(len(df))[::-1]
    ax.barh(y, df["pct"], color=[colori[g] for g in df["gruppo"]], height=0.66, edgecolor="white")
    for yi, p in zip(y, df["pct"]):
        ax.text(min(p, 100) + 1, yi, f"{p:.0f} %".replace(".", ","), va="center", fontsize=9, color=INK)
    ax.set_yticks(y, df["voce"])
    ax.set_xlim(0, 118)
    ax.set_xticks([0, 25, 50, 75, 100], ["0 %", "25 %", "50 %", "75 %", "100 %"])
    ax.set_xlabel(f"Quota delle {tot:,} celle d'Italia che hanno il dato".replace(",", "."))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color="#dddddd", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[
            Patch(color=colori["ovunque"], label="caricato su tutta Italia"),
            Patch(color=colori["aree"], label="c'è solo dentro le aree mappate dall'ente (fuori vale «nessuna area»)"),
            Patch(color=colori["mai"], label="previsto ma mai calcolato su questa installazione"),
        ],
        loc="lower center",
        bbox_to_anchor=(0.3, -0.36),
        frameon=False,
        fontsize=8.5,
    )
    ax.set_title("Quasi tutto il territorio è descritto; cinque dati previsti mancano", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "copertura.svg", transparent=False, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return df


# --- 2. mappe --------------------------------------------------------------------

LAT0 = np.cos(np.deg2rad(42.0))


def proietta(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return lon * LAT0 * 111.32, lat * 110.57


def confini() -> list[np.ndarray]:
    sql = "SELECT id, ST_AsGeoJSON(ST_Simplify(geom, 0.01), 4) AS g FROM aoi"
    df = pd.read_csv(io.StringIO(psql_copy(sql)))
    anelli: list[np.ndarray] = []
    for g in df["g"]:
        geo = json.loads(g)
        polys = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
        for poly in polys:
            ring = np.asarray(poly[0])
            x, yy = proietta(ring[:, 0], ring[:, 1])
            anelli.append(np.column_stack([x, yy]))
    return anelli


def celle() -> pd.DataFrame:
    sql = (
        "SELECT round(ST_X(g.centroid)::numeric, 4) AS lon, round(ST_Y(g.centroid)::numeric, 4) AS lat, "
        "round(f.slope_deg::numeric, 1) AS pendenza, f.flood_hazard_class AS idraulica "
        "FROM grid_cells g LEFT JOIN cell_static_factors f ON f.cell_id = g.id"
    )
    return pd.read_csv(io.StringIO(psql_copy(sql)))


def raster(df: pd.DataFrame, valori: np.ndarray, risoluzione_km: float = 1.2):
    x, y = proietta(df["lon"].to_numpy(), df["lat"].to_numpy())
    x0, y0 = x.min(), y.min()
    ix = ((x - x0) / risoluzione_km).astype(int)
    iy = ((y - y0) / risoluzione_km).astype(int)
    img = np.full((iy.max() + 1, ix.max() + 1), np.nan)
    # In caso di due celle nello stesso pixel vince il valore più alto: per la
    # pericolosità idraulica è la classe peggiore, come nel calcolo per cella.
    ordine = np.argsort(np.nan_to_num(valori, nan=-1))
    img[iy[ordine], ix[ordine]] = valori[ordine]
    estensione = (x0, x0 + img.shape[1] * risoluzione_km, y0, y0 + img.shape[0] * risoluzione_km)
    return img, estensione


def base_mappa(anelli: list[np.ndarray]):
    fig, ax = plt.subplots(figsize=(7.2, 8.2))
    for r in anelli:
        ax.plot(r[:, 0], r[:, 1], color="#555555", linewidth=0.35)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def figura_pendenza(df: pd.DataFrame, anelli: list[np.ndarray]) -> None:
    v = df["pendenza"].to_numpy(dtype=float)
    img, ext = raster(df, v)
    fig, ax = base_mappa(anelli)
    im = ax.imshow(img, origin="lower", extent=ext, cmap="cividis_r", vmin=0, vmax=35, interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, shrink=0.45, pad=0.01, extend="max")
    cb.set_label("pendenza media della cella (gradi)")
    ax.set_title("Dove il terreno è ripido: Alpi e Appennino si leggono da soli", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "mappa-pendenza.svg", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def figura_idraulica(df: pd.DataFrame, anelli: list[np.ndarray]) -> None:
    codici = {"P1": 1, "P2": 2, "P3": 3}
    v = df["idraulica"].map(codici).fillna(0).to_numpy(dtype=float)
    img, ext = raster(df, v)
    # Rampa del rischio di Limen: quasi-fondo, petrolio (bassa), giallo (media), rosso (alta).
    cmap = ListedColormap(["#ececec", "#3a8a8c", "#e8c547", "#c8432f"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
    fig, ax = base_mappa(anelli)
    ax.imshow(img, origin="lower", extent=ext, cmap=cmap, norm=norm, interpolation="nearest")
    n = df["idraulica"].value_counts()
    ax.legend(
        handles=[
            Patch(color="#c8432f", label=f"alta probabilità (P3): {n.get('P3', 0):,} celle".replace(",", ".")),
            Patch(color="#e8c547", label=f"media (P2): {n.get('P2', 0):,} celle".replace(",", ".")),
            Patch(color="#3a8a8c", label=f"bassa (P1): {n.get('P1', 0):,} celle".replace(",", ".")),
            Patch(color="#ececec", label="nessuna area mappata nella cella"),
        ],
        loc="lower left",
        frameon=False,
        fontsize=8.5,
        title="Area allagabile più grave che tocca la cella",
        title_fontsize=9,
    )
    ax.set_title("Le aree che possono allagarsi: pianure e fondovalle", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "mappa-idraulica.svg", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    df_cop = figura_copertura()
    print(df_cop.to_string(index=False), file=sys.stderr)
    anelli = confini()
    df = celle()
    figura_pendenza(df, anelli)
    figura_idraulica(df, anelli)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
