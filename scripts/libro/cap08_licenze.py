"""Capitolo 8, figura «licenze per dato»: che cosa chiede ogni fonte a chi ne usa i dati.

Disegna una matrice a punti: una riga per insieme di dati usato da Limen, una
colonna per obbligo (citare la fonte, ripubblicare i derivati con la stessa
licenza, riportare una frase o un'avvertenza precisa, licenza ancora da
chiarire).

Dati: la tabella delle licenze verificate fonte per fonte nella issue #406
(commento del 2026-11-07, https://github.com/agent-engineering-studio/limen/issues/406),
il catalogo `src/limen/config/dati.yaml` (IFFI CC BY-SA 4.0, verificate le 21
aree) e l'elenco delle fonti della mappa `frontend/src/lib/fonti.ts` (radar
DPC CC BY-SA 4.0, Sensor.Community DbCL «da confermare").
Le licenze non sono lette da rete: la tabella qui sotto è la trascrizione di
quelle fonti, da aggiornare quando cambiano.

Uscita: docs/book/figure/cap08/licenze-per-dato.svg
Uso: uv run --no-project --with matplotlib python -I scripts/libro/cap08_licenze.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RADICE = Path(__file__).resolve().parents[2]
USCITA = RADICE / "docs/book/figure/cap08/licenze-per-dato.svg"

COLONNE = [
    "Citare\nla fonte",
    "Ripubblicare ciò che\nne ricavi con la\nstessa licenza",
    "Riportare una frase\no un'avvertenza\nprecisa",
    "Licenza\nda chiarire",
]

# (dato, licenza, [cita, stessa licenza, frase/avvertenza, da chiarire])
RIGHE = [
    ("Frane censite IFFI (ISPRA)", "CC BY-SA 4.0", [1, 1, 0, 0]),
    ("Aree a pericolo di frana PAI (ISPRA)", "CC BY-SA 4.0", [1, 1, 1, 0]),
    ("Aree a pericolo di alluvione (ISPRA)", "CC BY-SA 4.0", [1, 1, 0, 0]),
    ("Radar pioggia (Protezione civile)", "CC BY-SA 4.0", [1, 1, 0, 0]),
    ("Strade e ferrovie (OpenStreetMap)", "ODbL 1.0", [1, 1, 0, 0]),
    ("Portata dei fiumi GloFAS (Copernicus)", "CEMS-Floods", [1, 0, 1, 0]),
    ("Previsioni ECMWF (meteo in casa)", "CC BY 4.0", [1, 0, 1, 0]),
    ("Uso del suolo CORINE, suolo impermeabile", "Copernicus", [1, 0, 1, 0]),
    ("Rilievo del terreno 5 m (CNR-IRPI)", "CC BY 4.0", [1, 0, 0, 0]),
    ("Confini comunali (ISTAT)", "CC BY 4.0", [1, 0, 0, 0]),
    ("Aree bruciate EFFIS", "CC BY 4.0", [1, 0, 0, 0]),
    ("Meteo Open-Meteo", "CC BY 4.0", [1, 0, 0, 0]),
    ("Fuochi attivi NASA FIRMS", "CC0 / uso libero", [1, 0, 0, 0]),
    ("Tipi di roccia (Ministero dell'Ambiente)", "CC BY 4.0 (?)", [1, 0, 0, 1]),
    ("Sensori Sensor.Community", "DbCL (?)", [1, 0, 0, 1]),
]

COLORI = ["#2a6f77", "#c9821b", "#7a5195", "#b23a48"]  # petrolio, ocra, viola, rosso
GRIGIO = "#d9d9d9"


def main() -> None:
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"], "svg.fonttype": "none"})
    n = len(RIGHE)
    fig, ax = plt.subplots(figsize=(10, 7.4), facecolor="white")
    ax.set_facecolor("white")
    for i, (_, _, obblighi) in enumerate(RIGHE):
        y = n - 1 - i
        for j, v in enumerate(obblighi):
            if v:
                ax.scatter(j, y, s=260, color=COLORI[j], zorder=3)
            else:
                ax.scatter(j, y, s=40, color=GRIGIO, zorder=2)
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{d}  ·  {lic}" for d, lic, _ in reversed(RIGHE)], fontsize=10)
    ax.set_xticks(range(len(COLONNE)))
    ax.set_xticklabels(COLONNE, fontsize=10)
    ax.xaxis.tick_top()
    ax.set_xlim(-0.5, len(COLONNE) - 0.5)
    ax.set_ylim(-0.7, n - 0.3)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="y", color="#eeeeee", zorder=0)
    fig.suptitle(
        "Tutti chiedono di essere citati; cinque chiedono di restare liberi anche dopo",
        fontsize=12.5,
        fontweight="bold",
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        0.015,
        "Punto pieno = obbligo presente. (?) = licenza con un punto ambiguo.  "
        "Fonte: issue #406 (2026-11-07), dati.yaml, fonti.ts.",
        fontsize=8.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    USCITA.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(USCITA, format="svg", facecolor="white")


if __name__ == "__main__":
    main()
