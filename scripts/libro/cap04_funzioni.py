"""Capitolo 4 — grafici delle funzioni dei tre motori, con i parametri veri.

Cosa disegna (in docs/book/figure/cap04/):
  classi.svg              le cinque classi dei tre pericoli, dai cutoff degli YAML
  frana_soglie.svg        la soglia di pioggia di Caine per macroregione, in mm cumulati
  frana_terreno_pioggia.svg  il punteggio frana in funzione di terreno (S) e pioggia (M)
  alluvione_inneschi.svg  la rampa pluviale (con il suolo) e la rampa fluviale
  alluvione_punteggio.svg il punteggio alluvione contro la pioggia, per tre suscettibilità
  incendio_fwi.svg        il punteggio incendio contro l'FWI, per sei coperture CORINE

Da quali dati: solo i file di configurazione del repository,
src/limen/config/hazards/{landslide,flood,wildfire}.yaml (wildfire-v1.1.0,
flood-v1.3.0, limen-deterministic-v1 al 2026-11-08). Le formule replicano
src/limen/core/scoring/ (engine.py, flood/trigger.py, flood/engine.py,
wildfire/engine.py). Nessun accesso al database o alla rete.

Esecuzione, dalla radice del repository:
  uv run --no-project --with matplotlib --with numpy --with pyyaml \
      python -I scripts/libro/cap04_funzioni.py
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

RADICE = Path(__file__).resolve().parents[2]
HAZ = RADICE / "src" / "limen" / "config" / "hazards"
OUT = RADICE / "docs" / "book" / "figure" / "cap04"
OUT.mkdir(parents=True, exist_ok=True)

# La rampa del rischio della mappa (frontend/src/lib/risk-colors.ts).
RAMPA = {
    "none": "#151c25",
    "low": "#134d47",
    "moderate": "#f2d45c",
    "high": "#f58a30",
    "very_high": "#e33f5a",
}
ETICHETTE = {
    "none": "nessuno",
    "low": "basso",
    "moderate": "moderato",
    "high": "alto",
    "very_high": "molto alto",
}
ORDINE = ["none", "low", "moderate", "high", "very_high"]
LINEE = ["#1b4f72", "#7d3c98", "#b9770e", "#117864", "#a93226", "#566573"]

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "svg.fonttype": "none",
    }
)


def carica(nome: str) -> dict:
    return yaml.safe_load((HAZ / f"{nome}.yaml").read_text(encoding="utf-8"))


FRANA = carica("landslide")
ALLUV = carica("flood")
INCEN = carica("wildfire")


def bande(ax, classi: dict, alpha: float = 0.13) -> None:
    """Fasce orizzontali delle classi sul punteggio (asse y)."""
    for k in ORDINE:
        lo, hi = classi[k]
        ax.axhspan(lo, hi, color=RAMPA[k], alpha=alpha if k != "none" else 0.06, lw=0)
        ax.text(
            1.005,
            (lo + hi) / 2,
            ETICHETTE[k],
            transform=ax.get_yaxis_transform(),
            va="center",
            ha="left",
            fontsize=8,
            color="#333",
        )


def salva(fig, nome: str) -> None:
    fig.savefig(OUT / nome, bbox_inches="tight")
    if anteprima := os.environ.get("LIBRO_ANTEPRIMA"):
        fig.savefig(Path(anteprima) / nome.replace(".svg", ".png"), bbox_inches="tight", dpi=80)
    plt.close(fig)
    print("scritto", OUT / nome)


# --------------------------------------------------------------- classi
def figura_classi() -> None:
    fig, ax = plt.subplots(figsize=(8, 2.6))
    righe = [
        ("Frana", FRANA["classes"]),
        ("Alluvione", ALLUV["classes"]),
        ("Incendio", INCEN["classes"]),
    ]
    for i, (_nome, cl) in enumerate(reversed(righe)):
        for k in ORDINE:
            lo, hi = cl[k]
            ax.barh(i, hi - lo, left=lo, color=RAMPA[k], edgecolor="white", height=0.6)
            colore_testo = "white" if k in ("none", "low") else "#111"
            if hi - lo >= 0.12:
                ax.text(
                    (lo + hi) / 2,
                    i,
                    ETICHETTE[k],
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=colore_testo,
                )
        for k in ORDINE[1:]:
            ax.text(
                cl[k][0],
                i + 0.36,
                f"{cl[k][0]:.2f}".replace(".", ","),
                ha="center",
                fontsize=7,
                color="#444",
            )
    ax.set_yticks(range(3), [r[0] for r in reversed(righe)])
    ax.set_xlim(0, 1)
    ax.set_xlabel("punteggio della cella (da 0 a 1)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title(
        "Dove il punteggio cambia classe: tre pericoli, tre scale", loc="left", fontsize=11
    )
    salva(fig, "classi.svg")


# --------------------------------------------------------------- frana
def figura_frana_soglie() -> None:
    macro = FRANA["caine"]["macroregions"]
    nomi = {
        "northern_italy": "Nord",
        "central_italy": "Centro (con Abruzzo e Molise)",
        "southern_italy": "Sud e Isole",
        "italy_default": "curva generica (aree non assegnate)",
    }
    d = np.linspace(1, 120, 400)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for (k, et), col in zip(nomi.items(), LINEE, strict=False):
        a, b = macro[k]["alpha"], macro[k]["beta"]
        mm = a * d ** (1 - b)  # intensità α·D^-β per la durata D = millimetri cumulati
        ax.plot(
            d,
            mm,
            color=col,
            lw=2 if k != "italy_default" else 1.4,
            ls="-" if k != "italy_default" else "--",
            label=et,
        )
    a, b = macro["southern_italy"]["alpha"], macro["southern_italy"]["beta"]
    v72 = a * 72 ** (1 - b)
    ax.plot([72], [v72], "o", color="#111")
    ax.annotate(
        f"Sud, 3 giorni: {v72:.0f} mm".replace(".", ","),
        (72, v72),
        xytext=(78, v72 - 14),
        fontsize=8.5,
        arrowprops={"arrowstyle": "-", "color": "#555"},
    )
    ax.set_xlabel("durata della pioggia (ore)")
    ax.set_ylabel("pioggia caduta dall'inizio (mm)")
    ax.set_xlim(0, 120)
    ax.set_ylim(0, None)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.set_title(
        "Quanta pioggia serve perché le frane comincino: più dura, più millimetri, ma ogni ora può essere più debole",
        loc="left",
        fontsize=10.5,
    )
    salva(fig, "frana_soglie.svg")


def figura_frana_terreno_pioggia() -> None:
    w = FRANA["weights"]
    cl = FRANA["classes"]
    s = np.linspace(0, 1, 301)
    m = np.linspace(0, 1, 301)
    S, M = np.meshgrid(s, m)
    punteggio = w["static"] * S + w["meteo"] * M  # terremoto, incendio e fiumi a zero
    limiti = [cl[k][0] for k in ORDINE] + [1.0]
    cmap = ListedColormap([RAMPA[k] for k in ORDINE])
    norm = BoundaryNorm(limiti, cmap.N)
    fig, ax = plt.subplots(figsize=(6.6, 5))
    ax.contourf(S, M, punteggio, levels=limiti, cmap=cmap, norm=norm, alpha=0.85)
    cs = ax.contour(S, M, punteggio, levels=limiti[1:-1], colors="white", linewidths=0.8)
    ax.clabel(cs, fmt=lambda v: f"{v:.2f}".replace(".", ","), fontsize=7)
    # Marche, maggio 2014: mediana delle 172 celle con frana nelle 72 h prima (issue #122).
    ax.plot([0.676], [0.468], "o", ms=7, mfc="white", mec="#111")
    ax.annotate(
        "Marche, maggio 2014:\nla cella tipica con una frana\n(punteggio 0,42, «moderato»)",
        (0.676, 0.468),
        xytext=(0.04, 0.80),
        fontsize=8.3,
        color="#111",
        bbox={"boxstyle": "round", "fc": "white", "ec": "#888", "alpha": 0.9},
        arrowprops={"arrowstyle": "->", "color": "#111"},
    )
    ax.text(
        0.98,
        0.985,
        "«molto alto» (0,75) solo con tutto al massimo,\nsenza un terremoto o un incendio recente",
        ha="right",
        va="top",
        fontsize=7.5,
        color="#111",
        bbox={"boxstyle": "round", "fc": "white", "ec": "#888", "alpha": 0.9},
    )
    ax.set_xlabel("quanto è fragile il terreno (0 = stabile, 1 = massimo)")
    ax.set_ylabel("quanto pesa la pioggia (0 = niente, 1 = massimo)")
    ax.legend(
        handles=[Patch(color=RAMPA[k], label=ETICHETTE[k]) for k in ORDINE],
        loc="lower right",
        fontsize=8,
        framealpha=0.9,
    )
    ax.set_title(
        "Frana: per arrivare ad «alto» servono terreno fragile e pioggia forte insieme",
        loc="left",
        fontsize=10,
    )
    salva(fig, "frana_terreno_pioggia.svg")


# --------------------------------------------------------------- alluvione
def rampa(x, lo, hi):
    return np.clip((x - lo) / (hi - lo), 0, 1)


def figura_alluvione_inneschi() -> None:
    p = ALLUV["pluvial"]
    f = ALLUV["fluvial"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.9))
    mm = np.linspace(0, 180, 500)
    base = rampa(mm, p["threshold_mm"], p["saturation_mm"])
    fattore = p["dry_soil_factor"]
    for et, umido, col in [
        ("suolo zuppo", 1.0, LINEE[0]),
        ("suolo non noto (a metà)", 0.5, LINEE[5]),
        ("suolo secco", 0.0, LINEE[2]),
    ]:
        a1.plot(mm, base * (fattore + (1 - fattore) * umido), color=col, lw=2, label=et)
    a1.axvline(p["threshold_mm"], color="#999", lw=0.8, ls=":")
    a1.axvline(p["saturation_mm"], color="#999", lw=0.8, ls=":")
    a1.text(p["threshold_mm"] + 2, 1.02, "40 mm", fontsize=8, color="#555")
    a1.text(p["saturation_mm"] + 2, 1.02, "120 mm", fontsize=8, color="#555")
    a1.set_xlabel("pioggia in 3 giorni (mm)")
    a1.set_ylabel("forza dell'innesco da pioggia (0-1)")
    a1.set_ylim(0, 1.08)
    a1.legend(frameon=False, fontsize=8, loc="lower right")
    a1.set_title("Pioggia: da 40 a 120 mm in tre giorni", loc="left", fontsize=10)

    r = np.linspace(0, 12, 500)
    a2.plot(r, rampa(r, f["normal_ratio"], f["saturation_ratio"]), color=LINEE[1], lw=2)
    a2.axvspan(0, 1.63, color="#999", alpha=0.12, lw=0)
    a2.text(
        0.1, 0.9, "9 giorni qualunque\nsu 10 stanno qui\n(sotto 1,63)", fontsize=8, color="#444"
    )
    a2.plot([6.39], [rampa(6.39, f["normal_ratio"], f["saturation_ratio"])], "o", color="#111")
    a2.annotate(
        "giorno di piena tipico\n(Romagna 2023-24): 6,4",
        (6.39, 0.57),
        xytext=(7.2, 0.3),
        fontsize=8,
        arrowprops={"arrowstyle": "-", "color": "#555"},
    )
    a2.set_xlabel("portata del fiume / sua piena ordinaria")
    a2.set_ylabel("forza dell'innesco dal fiume (0-1)")
    a2.set_ylim(0, 1.08)
    a2.set_title("Fiume: da 1,6 a 10 volte la piena ordinaria", loc="left", fontsize=10)
    fig.tight_layout()
    salva(fig, "alluvione_inneschi.svg")


def figura_alluvione_punteggio() -> None:
    p = ALLUV["pluvial"]
    cl = ALLUV["classes"]
    mm = np.linspace(0, 200, 500)
    innesco = rampa(mm, p["threshold_mm"], p["saturation_mm"])  # suolo zuppo, niente cemento
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    bande(ax, cl)
    for et, susc, col in [
        ("zona a pericolosità alta nel piano di bacino (0,80)", 0.80, LINEE[0]),
        ("zona a pericolosità media (0,50)", 0.50, LINEE[1]),
        (
            f"cella fuori dalle mappe ufficiali ({ALLUV['susceptibility']['unmapped']:.2f})".replace(
                ".", ","
            ),
            ALLUV["susceptibility"]["unmapped"],
            LINEE[2],
        ),
    ]:
        ax.plot(mm, susc * innesco, color=col, lw=2, label=et)
    ax.set_xlabel("pioggia in 3 giorni, su suolo zuppo (mm)")
    ax.set_ylabel("punteggio alluvione")
    ax.set_ylim(0, 1)
    ax.set_xlim(0, 200)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title(
        "Alluvione: la stessa pioggia pesa di più dove l'acqua sa già dove andare",
        loc="left",
        fontsize=10,
    )
    salva(fig, "alluvione_punteggio.svg")


# --------------------------------------------------------------- incendio
def peso_combustibile(codice: str) -> float:
    tab = INCEN["fuel"]["by_clc_prefix"]
    for n in range(len(codice), 0, -1):
        if codice[:n] in tab:
            return float(tab[codice[:n]])
    return float(INCEN["fuel"]["default"])


def figura_incendio() -> None:
    w = INCEN["weights"]
    fwi_max = INCEN["fwi"]["normalisation_max"]
    cl = INCEN["classes"]
    fwi = np.linspace(0, 60, 500)
    fwi_norm = np.minimum(fwi / fwi_max, 1)
    coperture = [
        ("312", "conifere"),
        ("323", "macchia mediterranea"),
        ("321", "praterie naturali"),
        ("311", "boschi di latifoglie"),
        ("211", "seminativi"),
        ("112", "tessuto urbano"),
    ]
    fig, ax = plt.subplots(figsize=(7.8, 4.4))
    bande(ax, cl)
    for (cod, et), col in zip(coperture, LINEE, strict=False):
        terreno = w["base"] + w["fuel"] * peso_combustibile(cod)  # pendenza nulla
        ax.plot(
            fwi,
            np.minimum(fwi_norm * terreno, 1),
            color=col,
            lw=2,
            label=f"{et} (combustibile {peso_combustibile(cod):.2f})".replace(".", ","),
        )
    ax.axvline(fwi_max, color="#999", lw=0.8, ls=":")
    ax.text(fwi_max + 0.5, 0.03, "FWI 50:\n«estremo»", fontsize=8, color="#555")
    ax.set_xlabel("indice meteo degli incendi (FWI)")
    ax.set_ylabel("punteggio incendio (terreno in piano)")
    ax.set_xlim(0, 60)
    ax.set_ylim(0, 1)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title(
        "Incendio: il tempo decide quanto, il bosco decide fin dove si può arrivare",
        loc="left",
        fontsize=10,
    )
    salva(fig, "incendio_fwi.svg")


if __name__ == "__main__":
    figura_classi()
    figura_frana_soglie()
    figura_frana_terreno_pioggia()
    figura_alluvione_inneschi()
    figura_alluvione_punteggio()
    figura_incendio()
