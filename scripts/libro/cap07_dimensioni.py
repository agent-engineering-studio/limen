"""Capitolo 7 — dove sta il peso del database.

Cosa disegna: `dimensioni.svg`, lo spazio su disco (dati più indici) delle
tabelle principali di Limen, sommando le partizioni giornaliere delle tabelle
partizionate. Un solo messaggio: quasi tutto il peso è ricalcolabile (storico dei
punteggi, strati ISPRA, stato corrente), mentre ciò che non si ricostruisce
sta nella copia notturna, di cui si mostra la dimensione dell'ultima riuscita
(riga `backup` di `limen-nightly` in `job_runs`).

Dati: catalogo di PostgreSQL (`pg_total_relation_size`, `pg_inherits`), in
sola lettura (transazione READ ONLY). Nessuna lettura delle tabelle stesse.
Installazione su Mac Intel con tutte le venti regioni. Misura del 2026-11-08.

    uv run --no-project --with matplotlib python -I scripts/libro/cap07_dimensioni.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap07"

SQL = """
BEGIN READ ONLY;
WITH parti AS (
  SELECT coalesce(i.inhparent::regclass::text, c.relname) AS tabella,
         pg_total_relation_size(c.oid) AS byte
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
  LEFT JOIN pg_inherits i ON i.inhrelid = c.oid
  WHERE c.relkind IN ('r', 'm')
)
SELECT tabella, sum(byte) FROM parti GROUP BY 1 ORDER BY 2 DESC LIMIT 12;
SELECT 'TOTALE', pg_database_size('limen');
SELECT 'BACKUP', (metrics->>'byte')::bigint FROM job_runs
 WHERE job_id = 'limen-nightly' AND scope = 'backup' AND status = 'ok'
 ORDER BY started_at DESC LIMIT 1;
ROLLBACK;
"""

# Nome interno → come lo chiamiamo nel libro, e se si ricostruisce da solo.
NOMI = {
    "risk_assessments": ("Storico dei punteggi (ultimi giorni)", True),
    "latest_risk": ("Punteggio attuale di ogni cella", True),
    "flood_hazard_subdiv": ("Aree allagabili ISPRA, a pezzi", True),
    "pai_hazard_subdiv": ("Aree di frana PAI, a pezzi", True),
    "flood_hazard": ("Aree allagabili ISPRA", True),
    "pai_hazard": ("Aree di frana PAI", True),
    "iffi_landslides": ("Inventario delle frane IFFI", True),
    "cell_static_factors": ("Com'è fatta ogni cella (fattori fissi)", True),
    "grid_cells": ("La griglia delle 312.550 celle", True),
    "mv_comune_risk": ("Riassunto per comune", True),
    "latest_forecast": ("Previsione per cella, 72 ore", True),
    "flood_events": ("Aree allagate viste dai satelliti", True),
    "osm_infrastructure": ("Strade e ferrovie (OpenStreetMap)", True),
    "comuni": ("Confini dei comuni", True),
    "cell_comune": ("Cella → comune", True),
    "app_cache": ("Copie temporanee delle risposte", True),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    out = subprocess.run(
        ["docker", "exec", "-i", "limen-postgres", "psql", "-U", "limen", "-d", "limen", "-q", "-At"],
        input=SQL,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    righe = [r.split("|") for r in out.splitlines() if "|" in r]
    totale = next(int(b) for t, b in righe if t == "TOTALE")
    backup = next(int(b) for t, b in righe if t == "BACKUP")
    tabelle = [(t, int(b)) for t, b in righe if t not in ("TOTALE", "BACKUP")][:10]
    for t, b in tabelle:
        print(f"{t:28s} {b / 1e9:6.2f} GB")
    print(f"TOTALE {totale / 1e9:.1f} GB")

    voci = [(NOMI.get(t, (t, True))[0], b / 1e9, True) for t, b in tabelle]
    voci.append(("La copia notturna di ciò che non si ricalcola", backup / 1e9, False))
    voci = voci[::-1]
    fig, ax = plt.subplots(figsize=(8.6, 4.8), facecolor="white")
    ax.barh(
        [v[0] for v in voci], [v[1] for v in voci],
        color=["#0072B2" if v[2] else "#D55E00" for v in voci], height=0.65,
    )
    for y, v in enumerate(voci):
        etichetta = f"{v[1]:.1f} GB" if v[1] >= 1 else f"{v[1] * 1000:.0f} MB"
        ax.text(v[1] + 0.05, y, etichetta.replace(".", ","), va="center", fontsize=8.5)
    ax.set_xlabel("gigabyte su disco, indici compresi", fontsize=9)
    ax.tick_params(axis="y", length=0, labelsize=9)
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)
    ax.set_title(
        f"{totale / 1e9:.0f} GB in tutto, quasi tutti ricalcolabili (blu);\n"
        "ciò che va salvato ogni notte sta in una copia da "
        f"{backup / 1e6:.0f} MB (arancio)",
        fontsize=11, loc="left",
    )
    fig.tight_layout()
    fig.savefig(OUT / "dimensioni.svg", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
