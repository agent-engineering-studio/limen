"""Il riepilogo notturno sulla qualità dei dati (#421): fatti, poi parole.

Ogni notte il passo ``qualita_dati`` raccoglie tre fatti dal database —
job falliti nelle ultime 24 ore, job in ritardo sulla loro cadenza, celle
non misurate per pericolo — e qui diventano un testo. È **deterministico**:
ogni cifra viene dai fatti, come nei riepiloghi regionali, e nessun modello
la tocca. Il paragrafo dell'AI (`agents/chat_agents/qualita_dati.py`)
riformula queste righe sopra di loro, non al loro posto.

La cadenza di un job non è scritta da nessuna parte: si ricava dalla sua
storia. Un job è in ritardo quando dall'ultimo successo è passato più di
:data:`FATTORE_RITARDO` volte il suo intervallo tipico degli ultimi trenta
giorni — il 90° percentile, non la mediana: lo sweep orario scrive una riga
per regione *per pericolo*, tre a pochi minuti l'una dall'altra, e la mediana
diceva «ogni 2 minuti» a un job che gira ogni ora. Così un job nuovo è
sorvegliato senza configurarlo, e uno che gira ogni ora non aspetta un giorno
per sembrare fermo.

Un job con una riga nazionale (``scope`` vuoto) si giudica su quella: le sue
righe per regione possono tacere per giorni senza guasto — il nowcast gira su
una regione solo quando il radar vi vede pioggia — e se una regione fallisce
lo dicono gli errori.

Puro: i fatti arrivano già letti da ``data/repos/qualita_dati_repo.py``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

#: Quante volte l'intervallo mediano prima di dire «in ritardo». Due: un
#: tick saltato non è un allarme, due di fila sì.
FATTORE_RITARDO = 2.0
#: Sotto questi intervalli osservati la cadenza non si giudica.
MIN_INTERVALLI = 3
#: Una quota di celle non misurate che sale di più di così in una settimana
#: si segnala anche sotto la metà.
SALTO_NON_MISURATO = 0.05


_SEGRETO = re.compile(r"(?i)\b(key|map_key|apikey|api_key|token|password|secret)=([^&\s'\"]+)")


def pulisci(messaggio: str) -> str:
    """Il messaggio d'errore senza i segreti di un URL (un 4xx di FIRMS porta la chiave)."""
    return _SEGRETO.sub(r"\1=<nascosto>", messaggio)


@dataclass(frozen=True, slots=True)
class Errore:
    job_id: str
    scope: str | None
    volte: int
    ultimo: datetime
    messaggio: str | None


@dataclass(frozen=True, slots=True)
class Cadenza:
    job_id: str
    scope: str | None
    ultimo_successo: datetime
    intervallo: timedelta
    intervalli: int


@dataclass(frozen=True, slots=True)
class Ritardo:
    job_id: str
    scope: str | None
    ultimo_successo: datetime
    eta: timedelta
    intervallo: timedelta


@dataclass(frozen=True, slots=True)
class Fatti:
    adesso: datetime
    errori: Sequence[Errore]
    cadenze: Sequence[Cadenza]
    #: pericolo → (celle non misurate, celle con un punteggio)
    non_misurate: Mapping[str, tuple[int, int]]

    def ritardi(self) -> list[Ritardo]:
        out: list[Ritardo] = []
        nazionali = {c.job_id for c in self.cadenze if c.scope is None}
        for c in self.cadenze:
            if c.scope is not None and c.job_id in nazionali:
                continue
            if c.intervalli < MIN_INTERVALLI or c.intervallo <= timedelta(0):
                continue
            eta = self.adesso - c.ultimo_successo
            if eta > c.intervallo * FATTORE_RITARDO:
                out.append(Ritardo(c.job_id, c.scope, c.ultimo_successo, eta, c.intervallo))
        return sorted(out, key=lambda r: r.eta / r.intervallo, reverse=True)

    def quote_non_misurate(self) -> dict[str, float]:
        return {h: (n / tot if tot else 0.0) for h, (n, tot) in self.non_misurate.items()}

    def metriche(self) -> dict[str, object]:
        """Ciò che resta in ``job_runs.metrics``: la settimana dopo è il confronto."""
        return {
            "errori": sum(e.volte for e in self.errori),
            "job_con_errori": len({e.job_id for e in self.errori}),
            "in_ritardo": [_nome(r.job_id, r.scope) for r in self.ritardi()],
            "non_misurate": {h: round(q, 4) for h, q in self.quote_non_misurate().items()},
        }


def _nome(job_id: str, scope: str | None) -> str:
    return f"{job_id} ({scope})" if scope else job_id


def _soggetto(job_id: str, scope: Sequence[str | None]) -> tuple[str, str]:
    """Il nome in grassetto e, per un gruppo, « in N ambiti (a, b, …)»."""
    if len(scope) == 1:
        return f"**{_nome(job_id, scope[0])}**", ""
    nomi = sorted({x for x in scope if x})
    elenco = ", ".join(nomi[:5]) + (f" e altri {len(nomi) - 5}" if len(nomi) > 5 else "")
    return f"**{job_id}**", f" in {len(scope)} ambiti ({elenco})"


def _durata(d: timedelta) -> str:
    ore = d.total_seconds() / 3600
    if ore < 1:
        return f"{round(d.total_seconds() / 60)} min"
    if ore < 48:
        return f"{ore:.0f} h"
    return f"{ore / 24:.0f} giorni"


def _quota(q: float) -> str:
    return f"{q * 100:.1f}".replace(".", ",") + " %"


def righe(fatti: Fatti, settimana_prima: Mapping[str, object] | None) -> list[str]:
    """Il riepilogo in italiano, una riga per problema; vuoto se va tutto bene."""
    out: list[str] = []
    # Raggruppati per job (e per messaggio, gli errori): un guasto che ferma
    # lo sweep di tutte le regioni è un guasto, non venti righe uguali.
    fermi: dict[str, list[Ritardo]] = {}
    for r in fatti.ritardi():
        fermi.setdefault(r.job_id, []).append(r)
    for job_id, gruppo in fermi.items():
        peggiore = max(gruppo, key=lambda r: r.eta)
        chi, dove = _soggetto(job_id, [r.scope for r in gruppo])
        out.append(
            f"{chi} è fermo{dove}: ultimo successo {_durata(peggiore.eta)} fa, "
            f"di solito gira ogni {_durata(peggiore.intervallo)}."
        )
    falliti: dict[tuple[str, str | None], list[Errore]] = {}
    for e in fatti.errori:
        falliti.setdefault((e.job_id, e.messaggio), []).append(e)
    for (job_id, messaggio), stessi in sorted(
        falliti.items(), key=lambda kv: sum(e.volte for e in kv[1]), reverse=True
    ):
        totale = sum(e.volte for e in stessi)
        ultimo = max(e.ultimo for e in stessi)
        testo_msg = f": «{messaggio[:200]}»" if messaggio else ""
        volte = "una volta" if totale == 1 else f"{totale} volte"
        chi, dove = _soggetto(job_id, [e.scope for e in stessi])
        out.append(
            f"{chi} è fallito{dove} {volte} nelle ultime 24 ore, "
            f"l'ultima alle {ultimo:%H:%M} UTC{testo_msg}."
        )
    prima: Mapping[str, object] = {}
    if settimana_prima is not None:
        valore = settimana_prima.get("non_misurate")
        if isinstance(valore, Mapping):
            prima = valore
    for hazard, quota in sorted(fatti.quote_non_misurate().items()):
        vecchia = prima.get(hazard)
        salita = isinstance(vecchia, int | float) and quota - float(vecchia) > SALTO_NON_MISURATO
        if quota < 0.5 and not salita:
            continue
        riga = f"Pericolo **{hazard}**: {_quota(quota)} delle celle non misurate"
        if isinstance(vecchia, int | float):
            riga += f" (una settimana fa {_quota(float(vecchia))})"
        out.append(riga + ": manca il dato meteo, non è quiete.")
    return out


def testo(
    fatti: Fatti, settimana_prima: Mapping[str, object] | None, sintesi: str | None = None
) -> str:
    """Il report; ``sintesi`` è il paragrafo dell'AI, che va sopra le righe e non al loro posto."""
    problemi = righe(fatti, settimana_prima)
    testa = [f"# Qualità dei dati — {fatti.adesso:%Y-%m-%d %H:%M} UTC", ""]
    if not problemi:
        return "\n".join(
            [
                *testa,
                "Niente da segnalare: nessun job fermo o fallito, "
                "nessun pericolo con metà delle celle non misurate.",
            ]
        )
    if sintesi:
        testa += [sintesi, "", "_Riformulato dall'AI dalle righe qui sotto, che fanno fede._", ""]
    return "\n".join([*testa, *(f"- {p}" for p in problemi)])


__all__ = [
    "FATTORE_RITARDO",
    "Cadenza",
    "Errore",
    "Fatti",
    "Ritardo",
    "pulisci",
    "righe",
    "testo",
]
