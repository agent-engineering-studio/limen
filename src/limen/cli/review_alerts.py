"""``limen review-alerts`` — checklist di verifica manuale degli alert (#59).

Il tasso di falsi positivi non si misura da soli. Un backtest dice se un
alert è arrivato prima di un evento *registrato in un inventario*, ma gli
inventari italiani sono incompleti per costruzione — una frana in un bosco
senza strade non entra da nessuna parte. Quindi il FAR percepito lo può dire
solo chi conosce il territorio, e questo comando gli prepara il foglio: un
campione casuale di alert recenti, uno per riga, con lo spazio per scrivere
"c'era" o "non c'era".

Casuale e non "i più recenti": gli alert recenti sono correlati fra loro (uno
stesso fronte meteo), e un campione correlato non misura il tasso di falsi
positivi — misura un temporale.

Il report è markdown su file, non a schermo: va compilato e archiviato, ed è
il documento che rende il numero difendibile davanti a un'istituzione.

Variabili: ``LIMEN_REVIEW_SAMPLE`` (default 20), ``LIMEN_REVIEW_DAYS``
(default 30), ``LIMEN_REVIEW_OUT`` (default ``reports/review-alerts-<data>.md``).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.repos.alert_aggregates_repo import sample_recent

log = get_logger(__name__)

_HAZARD_LABEL_IT = {
    "landslide": "frana",
    "flood": "alluvione",
    "wildfire": "incendio",
}

_LEVEL_LABEL_IT = {
    "None": "nessuno",
    "Low": "basso",
    "Moderate": "moderato",
    "High": "alto",
    "VeryHigh": "molto alto",
}


def render_review_markdown(
    rows: list[dict[str, Any]],
    *,
    days: int,
    generated_at: datetime,
) -> str:
    """Il foglio di verifica. Deterministico: solo ciò che c'è nelle righe."""
    testa = [
        "# Verifica campionaria degli alert",
        "",
        f"Generato il {generated_at:%d/%m/%Y alle %H:%M} UTC · "
        f"campione di {len(rows)} allerte sugli ultimi {days} giorni.",
        "",
        "## Come si compila",
        "",
        "Per ogni riga, chi conosce il territorio scrive **una** delle tre:",
        "",
        "- `confermato` — in quell'area, in quella finestra, è accaduto qualcosa",
        "  di coerente con il pericolo segnalato (anche senza danni).",
        "- `falso positivo` — non è accaduto nulla di coerente.",
        "- `non verificabile` — non ci sono elementi per dirlo (area non",
        "  raggiungibile, nessun osservatore, nessuna segnalazione).",
        "",
        "Il tasso di falsi positivi si calcola **escludendo** le righe non",
        "verificabili dal denominatore: contarle come conferme gonfierebbe la",
        "resa del sistema, contarle come falsi positivi la affosserebbe, e in",
        "entrambi i casi il numero direbbe qualcosa che nessuno ha osservato.",
        "",
    ]

    if not rows:
        return "\n".join(
            [
                *testa,
                "## Campione",
                "",
                "Nessuna allerta nella finestra richiesta: niente da verificare.",
                "",
            ]
        )

    tabella = [
        "## Campione",
        "",
        "| # | data (UTC) | comune | pericolo | livello | aree | max | esito | note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        creato = r["created_at"]
        quando = creato.strftime("%d/%m %H:%M") if isinstance(creato, datetime) else str(creato)
        comune = r["comune"] or "area non attribuita"
        pericolo = _HAZARD_LABEL_IT.get(str(r["hazard_type"]), str(r["hazard_type"]))
        livello = _LEVEL_LABEL_IT.get(str(r["max_level"]), str(r["max_level"]))
        tabella.append(
            f"| {i} | {quando} | {comune} | {pericolo} | {livello} | "
            f"{r['cells_count']} | {float(r['max_score']):.2f} |  |  |"
        )

    coda = [
        "",
        "## Dettaglio delle celle",
        "",
        "Le celle nominate per ogni riga, per chi vuole andare sul punto esatto.",
        "",
    ]
    for i, r in enumerate(rows, 1):
        celle = r["top_cells"] or []
        elenco = (
            ", ".join(f"`{c['cell_id']}` ({float(c['score']):.2f})" for c in celle)
            if celle
            else "—"
        )
        coda.append(f"{i}. {r['comune'] or 'area non attribuita'}: {elenco}")

    calcolo = [
        "",
        "## Esito",
        "",
        "Compilata la colonna «esito», il tasso è:",
        "",
        "```",
        "falsi positivi / (confermati + falsi positivi)",
        "```",
        "",
        "Riportarlo sempre con il denominatore accanto: «3 su 17 verificabili»",
        "dice quanto vale il numero, «18 %» no.",
        "",
    ]
    return "\n".join([*testa, *tabella, *coda, *calcolo])


async def run() -> int:
    settings = get_settings()
    sample = int(os.getenv("LIMEN_REVIEW_SAMPLE", "20"))
    days = int(os.getenv("LIMEN_REVIEW_DAYS", "30"))
    generated_at = datetime.now(UTC)

    async with lifespan_pool(settings.db):
        rows = await sample_recent(limit=sample, since=timedelta(days=days))

    out_env = os.getenv("LIMEN_REVIEW_OUT")
    out = Path(out_env) if out_env else Path("reports") / f"review-alerts-{generated_at:%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_review_markdown(rows, days=days, generated_at=generated_at),
        encoding="utf-8",
    )

    log.info(
        "review_alerts.done",
        path=str(out),
        sampled=len(rows),
        requested=sample,
        days=days,
    )
    if not rows:
        log.warning(
            "review_alerts.empty",
            hint=f"nessuna allerta negli ultimi {days} giorni: alza LIMEN_REVIEW_DAYS",
        )
    return 0


__all__ = ["render_review_markdown", "run"]
