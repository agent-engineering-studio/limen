"""Appendice E — il radar da vicino: tre figure.

Cosa disegna (in docs/book/figure/appE/):
  come-vede-il-radar.svg  il fascio del radar in scala, e quattro motivi per cui
                          perde pioggia o ne vede troppa
  melito-orarie.svg       la pioggia di cinque ore a Melito di Porto Salvo, il
                          10 ottobre 2026: radar da solo e corretta con i pluviometri
  allerta-e-pioggia.svg   la pioggia misurata il 10 ottobre 2026 nelle zone di
                          allerta, secondo il colore annunciato il giorno prima

Da quali dati:
  - il fascio è geometria, senza dati: altezza = r·sin(a) + r²/(2·4/3·R), la
    regola dei «4/3 del raggio terrestre», con il fascio più basso a 0,5° e
    largo un grado. Montagna, nuvola e fascia di fusione sono un esempio;
  - le piogge orarie sono trascritte dal quaderno
    notebooks/04_hourly_rain_archive.ipynb di dpc-radar 0.2.1, eseguito il
    15 novembre 2026 (prodotti SRT1 e CUM3 del DPC, punto 15,78°E 37,92°N);
  - le piogge per zona sono trascritte dal quaderno
    notebooks/05_alert_vs_radar.ipynb, eseguito il 15 novembre 2026 (bollettino
    del DPC emesso il 9 ottobre 2026 alle 16:15, prodotto CUM24 delle 00:00 UTC
    dell'11 ottobre). Dati © Dipartimento della Protezione Civile: radar
    CC BY-SA 4.0, bollettino CC BY 4.0.
Nessun accesso alla rete: qui si ridisegna soltanto.

Esecuzione, dalla radice del repository:
  uv run --no-project --with matplotlib --with numpy python -I scripts/libro/appE_radar.py
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse

RADICE = Path(__file__).resolve().parents[2]
OUT = RADICE / "docs" / "book" / "figure" / "appE"
OUT.mkdir(parents=True, exist_ok=True)

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

BLU, BLU_CHIARO, GRIGIO, TERRA, NERO = "#1f618d", "#9ec5f4", "#99a3a4", "#d9d6cc", "#0b0b0b"
RAGGIO_TERRA_KM = 6371.0


def salva(fig, nome: str) -> None:
    fig.savefig(OUT / nome, bbox_inches="tight")
    if anteprima := os.environ.get("LIBRO_ANTEPRIMA"):
        fig.savefig(Path(anteprima) / nome.replace(".svg", ".png"), bbox_inches="tight", dpi=80)
    plt.close(fig)
    print("scritto", OUT / nome)


def quota_km(distanza: np.ndarray, angolo_gradi: float) -> np.ndarray:
    """Quota del fascio sopra il radar, in km (regola dei 4/3 del raggio terrestre)."""
    return distanza * np.sin(np.radians(angolo_gradi)) + distanza**2 / (2 * 4 / 3 * RAGGIO_TERRA_KM)


def nota(ax, n: int, x: float, y: float, testo: str) -> None:
    ax.text(x, y, str(n), ha="center", va="center", fontsize=9, color="white", weight="bold",
            bbox={"boxstyle": "circle,pad=0.25", "fc": NERO, "ec": "none"}, zorder=9)  # fmt: skip
    ax.text(x + 4, y, testo, ha="left", va="center", fontsize=9, zorder=9)


def come_vede_il_radar() -> None:
    r = np.linspace(0, 220, 400)
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    ax.axhspan(2.9, 3.4, color="#f3d9a4", alpha=0.7, zorder=1)  # la neve che fonde

    basso, centro, alto = quota_km(r, 0.0), quota_km(r, 0.5), quota_km(r, 1.0)
    ax.fill_between(r, basso, alto, color=BLU_CHIARO, alpha=0.55, zorder=2, linewidth=0)
    ax.plot(r, centro, color=BLU, linewidth=1.2, zorder=3)

    # Una montagna vicina nasconde la parte del fascio che parte sotto la sua cima.
    cima_km, cima_quota = 60.0, 0.8
    coperto = np.degrees(np.arcsin((cima_quota - quota_km(np.array(cima_km), 0.0)) / cima_km))
    dietro = r > cima_km
    ax.fill_between(r[dietro], basso[dietro], quota_km(r[dietro], float(coperto)), color="white",
                    alpha=0.85, zorder=3, linewidth=0)  # fmt: skip
    ax.fill([cima_km - 14, cima_km, cima_km + 14], [0, cima_quota, 0], color=TERRA, zorder=4)

    # Una nuvola bassa e lontana: la pioggia cade sotto il fascio.
    for cx, cy in ((146, 1.45), (158, 1.6), (170, 1.45)):
        ax.add_patch(Ellipse((cx, cy), 22, 0.75, color="#b9b8b2", zorder=5))
    for x in np.arange(141, 177, 3.5):
        ax.plot([x, x - 1.5], [1.1, 0.1], color=BLU, linewidth=1.3, zorder=5)
    ax.plot([158, 158], [0, 0.4], color=NERO, linewidth=2, zorder=6)
    ax.plot([155.5, 160.5], [0.4, 0.4], color=NERO, linewidth=2, zorder=6)

    ax.plot([0, 0], [0, 0.35], color=NERO, linewidth=3, zorder=6)
    ax.add_patch(Ellipse((0, 0.45), 6, 0.36, color=NERO, zorder=6))
    ax.axhline(0, color=NERO, linewidth=1.5, zorder=6)
    ax.set_xlim(-6, 222)
    ax.set_ylim(0, 6.6)
    ax.set_xlabel("distanza dal radar (km)")
    ax.set_ylabel("quota sopra il radar (km)")
    ax.text(-3, 0.8, "radar", fontsize=9)
    ax.text(179, 0.25, "pluviometro", fontsize=9, ha="left")

    nota(ax, 1, 96, float(quota_km(np.array(100.0), 0.5)) + 0.75,
         "il fascio sale: a 100 km è già a 1,5 km di quota")  # fmt: skip
    nota(ax, 2, 150, 5.0, "e a 200 km è a 4 km")
    nota(ax, 3, 78, 0.3, "dietro una montagna\nmetà del fascio non passa")
    nota(ax, 4, 14, 3.15, "la neve che fonde brilla come un nubifragio")
    nota(ax, 5, 183, 1.3, "la pioggia che nasce in basso\ncade sotto il fascio")
    ax.set_title("Perché un radar può perdere pioggia, o vederne troppa", loc="left", fontsize=11)
    salva(fig, "come-vede-il-radar.svg")


# Ora di fine (UTC), radar da solo (SRT1), corretta con i pluviometri (mm).
# Quaderno 04 di dpc-radar, eseguito il 15 novembre 2026.
ORE = [("01:00", 16.0, 47.4), ("02:00", 21.2, 63.0), ("03:00", 8.3, 24.6),
       ("04:00", 20.3, 6.3), ("05:00", 17.7, 5.5)]  # fmt: skip


def melito_orarie() -> None:
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(ORE))
    solo = [o[1] for o in ORE]
    corretta = [o[2] for o in ORE]
    ax.bar(x - 0.2, solo, 0.4, color=GRIGIO, label="radar da solo")
    ax.bar(x + 0.2, corretta, 0.4, color=BLU, label="corretta con i pluviometri")
    for xi, a, b in zip(x, solo, corretta, strict=True):
        ax.text(xi - 0.2, a + 1, f"{a:.0f}".replace(".", ","), ha="center", fontsize=8.5)
        ax.text(xi + 0.2, b + 1, f"{b:.0f}".replace(".", ","), ha="center", fontsize=8.5)
    ax.axhline(30, color="#c0392b", linewidth=1, linestyle="--")
    ax.text(len(ORE) - 0.45, 31.5, "30 mm in un'ora", color="#c0392b", fontsize=8.5, ha="right")
    ax.set_xticks(x, [o[0] for o in ORE])
    ax.set_xlabel("ora che finisce alle… (UTC, 10 ottobre 2026)")
    ax.set_ylabel("pioggia in un'ora (mm)")
    ax.set_ylim(0, 72)
    ax.legend(frameon=False, loc="upper right")
    ax.set_title("Melito di Porto Salvo: la stessa pioggia, due letture", loc="left", fontsize=11)
    fig.text(0.01, -0.04, "Dati: Dipartimento della Protezione Civile, CC BY-SA 4.0 "
             "(SRT1 e CUM3), letti con dpc-radar.", fontsize=7.5, color="#566573")  # fmt: skip
    salva(fig, "melito-orarie.svg")


# Colore annunciato per il 10 ottobre, numero di zone, pioggia media tipica e
# picco tipico nelle zone di quel colore (mediana fra le zone, mm in 24 ore).
# Quaderno 05 di dpc-radar, eseguito il 15 novembre 2026.
ZONE = [("nessuna allerta", 128, 0, 0, "#abb2b9"), ("gialla", 40, 11, 28, "#f1c40f"),
        ("arancione", 19, 28, 75, "#e67e22")]  # fmt: skip


def allerta_e_pioggia() -> None:
    fig, ax = plt.subplots(figsize=(8, 3.4))
    y = np.arange(len(ZONE))
    for yi, (_, _, media, picco, colore) in zip(y, ZONE, strict=True):
        ax.barh(yi + 0.18, picco, 0.34, color=colore, alpha=0.45)
        ax.barh(yi - 0.18, media, 0.34, color=colore)
        ax.text(picco + 1, yi + 0.18, f"picco {picco} mm", va="center", fontsize=8.5)
        ax.text(media + 1, yi - 0.18, f"media {media} mm", va="center", fontsize=8.5)
    ax.set_yticks(y, [f"{nome}\n({n} zone)" for nome, n, *_ in ZONE])
    ax.set_xlabel("pioggia misurata in 24 ore, valore tipico fra le zone (mm)")
    ax.set_xlim(0, 95)
    ax.set_title("10 ottobre 2026: l'allerta annunciata e la pioggia caduta", loc="left",
                 fontsize=11)  # fmt: skip
    fig.text(0.01, -0.06, "Dati: Dipartimento della Protezione Civile. Bollettino del 9 ottobre "
             "2026, CC BY 4.0; pioggia «Merging», CC BY-SA 4.0.", fontsize=7.5, color="#566573")  # fmt: skip
    salva(fig, "allerta-e-pioggia.svg")


if __name__ == "__main__":
    come_vede_il_radar()
    melito_orarie()
    allerta_e_pioggia()
