"""Capitolo 7 — una giornata di Limen, dal registro dei lavori.

Cosa disegna:
  1. `giornata.svg`: tutti i lavori automatici partiti il 7 novembre 2026
     (giornata UTC), uno per riga, con l'inizio e la durata vera. Ogni barra è
     una corsa registrata in `job_runs` (solo le righe complessive, non quelle
     per regione); le corse più corte di qualche minuto sono allargate a 4
     minuti perché restino visibili.
  2. `tempi_sweep.svg`: quanto dura il calcolo orario nazionale (tre pericoli,
     312.550 celle) in ogni corsa dal 6 all'8 novembre 2026, contro i 60
     minuti che ha a disposizione.

Dati: tabella `job_runs` del database di Limen, in sola lettura (transazione
READ ONLY), installazione su Mac Intel con tutte le venti regioni. Misura del
2026-11-08.

    uv run --no-project --with matplotlib python -I scripts/libro/cap07_giornata.py
"""

from __future__ import annotations

import csv
import io
import subprocess
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[2] / "docs" / "book" / "figure" / "cap07"

SQL_GIORNO = """
BEGIN READ ONLY;
COPY (
  SELECT job_id, started_at AT TIME ZONE 'UTC',
         extract(epoch FROM coalesce(finished_at, started_at) - started_at)
  FROM job_runs
  WHERE started_at >= '2026-11-07' AND started_at < '2026-11-08'
    AND (scope IS NULL OR scope = '')
    AND job_id <> 'limen-worker-heartbeat'
  ORDER BY started_at
) TO STDOUT WITH CSV;
ROLLBACK;
"""

SQL_SWEEP = """
BEGIN READ ONLY;
COPY (
  SELECT started_at AT TIME ZONE 'UTC',
         extract(epoch FROM finished_at - started_at), status
  FROM job_runs
  WHERE job_id = 'limen-hourly-monitoring' AND (scope IS NULL OR scope = '')
    AND finished_at IS NOT NULL
    AND started_at >= now() - interval '7 days'
  ORDER BY started_at
) TO STDOUT WITH CSV;
ROLLBACK;
"""

# (job, etichetta per chi legge, colore). Ordine = riga dall'alto.
RIGHE = [
    ("limen-hourly-monitoring", "Le tre mappe, ogni ora", "#D55E00"),
    ("limen-nowcast-monitoring", "Controllo del radar (pioggia forte?)", "#E69F00"),
    ("limen-forecast-history", "Previsione cella per cella, 72 ore", "#0072B2"),
    ("limen-forecast-monitoring", "Avvisi di previsione", "#56B4E9"),
    ("limen-nightly", "Lavori della notte (misure, manutenzione, copia)", "#555555"),
    ("limen-briefing-enrichment", "Testi spiegati delle regioni", "#CC79A7"),
    ("limen-dpc-bollettini", "Bollettini della Protezione civile", "#009E73"),
    ("limen-html-report", "Pagina di riepilogo", "#999999"),
    ("limen-daily-report", "Rapporto del mattino", "#999999"),
    ("limen-raccolta-eventi", "Notizie di eventi dai giornali", "#999999"),
    ("limen-fedelta-racconti", "Revisione dei testi", "#999999"),
]


def query(sql: str) -> list[list[str]]:
    out = subprocess.run(
        ["docker", "exec", "-i", "limen-postgres", "psql", "-U", "limen", "-d", "limen", "-q", "-At"],
        input=sql,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    righe = [r for r in out.splitlines() if r and not r.startswith(("BEGIN", "ROLLBACK"))]
    return list(csv.reader(io.StringIO("\n".join(righe))))


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def figura_giornata() -> None:
    corse = query(SQL_GIORNO)
    indice = {job: i for i, (job, _, _) in enumerate(RIGHE)}
    fig, ax = plt.subplots(figsize=(10, 4.8), facecolor="white")
    for job, inizio, durata in corse:
        if job not in indice:
            continue
        i = indice[job]
        t0 = ts(inizio)
        minuti = max(float(durata) / 60.0, 4.0)
        ax.barh(
            len(RIGHE) - 1 - i,
            minuti / 1440.0,
            left=mdates.date2num(t0),
            height=0.6,
            color=RIGHE[i][2],
            linewidth=0,
        )
    ax.set_yticks(range(len(RIGHE)))
    ax.set_yticklabels([r[1] for r in RIGHE][::-1], fontsize=9)
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 25, 3)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_xlim(mdates.date2num(datetime(2026, 11, 7)), mdates.date2num(datetime(2026, 11, 8)))
    ax.set_xlabel("Ora del 7 novembre 2026 (tempo universale; in Italia un'ora in più)", fontsize=9)
    ax.grid(axis="x", color="#e5e5e5")
    ax.set_axisbelow(True)
    for lato in ("top", "right", "left"):
        ax.spines[lato].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title(
        "Una giornata vera: le mappe ogni ora, la previsione quattro volte, la notte una volta",
        fontsize=11.5, loc="left",
    )
    fig.tight_layout()
    fig.savefig(OUT / "giornata.svg", bbox_inches="tight")
    plt.close(fig)


def figura_sweep() -> None:
    corse = [(ts(a), float(d) / 60.0, s) for a, d, s in query(SQL_SWEEP)]
    ok = [(t, m) for t, m, s in corse if s == "ok"]
    fig, ax = plt.subplots(figsize=(9, 3.6), facecolor="white")
    ax.axhline(60, color="#D55E00", linewidth=1.2, linestyle="--")
    ax.text(
        mdates.date2num(ok[0][0]), 61.5, "il tempo a disposizione: 60 minuti",
        color="#D55E00", fontsize=9,
    )
    ax.bar(
        [mdates.date2num(t) for t, _ in ok], [m for _, m in ok],
        width=0.03, color="#0072B2",
    )
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    ax.set_ylabel("minuti per corsa", fontsize=9)
    ax.set_ylim(0, 70)
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)
    mediana = sorted(m for _, m in ok)[len(ok) // 2]
    ax.set_title(
        f"Il calcolo di tutta Italia sta dentro l'ora: metà delle corse dura meno di {mediana:.0f} minuti",
        fontsize=11, loc="left",
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(OUT / "tempi_sweep.svg", bbox_inches="tight")
    plt.close(fig)
    print(f"corse ok={len(ok)} mediana={mediana:.1f} min max={max(m for _, m in ok):.1f} min")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    figura_giornata()
    figura_sweep()


if __name__ == "__main__":
    main()
