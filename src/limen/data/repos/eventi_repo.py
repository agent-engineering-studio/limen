"""Le query a cursore degli eventi MCP (#371). Sola lettura.

Ogni ``events/poll`` è autosufficiente: nome, argomenti e cursore bastano a
rispondere, e il server non ricorda niente. Il cursore è ``(istante, id)``
dell'ultima riga consegnata, e le righe si leggono in quell'ordine.

**Il margine.** ``computed_at`` è il ``now()`` d'inizio della transazione
che scrive, non del commit: una riga può comparire dopo righe con un istante
più recente. Per non saltarla, le valutazioni si leggono solo fino a
:data:`MARGINE` fa: un evento arriva al più così tardi, mai perso. Le allerte
le spedisce un solo worker, una alla volta (``id`` crescente al commit), e il
margine non serve.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from limen.core.eventi import (
    ALLERTA,
    CAMBIO_CLASSE,
    PREVISIONE,
    Filtro,
    Posizione,
    codifica,
    decodifica,
    filtro,
    id_evento,
    livelli_da,
    payload,
)
from limen.data.db import acquire

#: Quanto indietro resta la lettura delle valutazioni (vedi il modulo).
MARGINE = timedelta(minutes=15)
#: ``risk_assessments`` tiene 14 giorni: prima non c'è niente da rileggere.
STORIA = timedelta(days=14)
EVENTI_PREDEFINITI = 100
EVENTI_MASSIMI = 500
#: Ogni quanto conviene richiedere: lo sweep è orario, le allerte lo seguono.
PROSSIMA_RICHIESTA_MS = 300_000

_ALLERTE_SQL = """
SELECT a.id, a.dispatched_at AS t, a.cell_id, a.aoi_id, a.hazard_type::text AS hazard,
       a.level, a.score, a.summary
FROM alert_dispatches a
WHERE (a.dispatched_at, a.id) > ($1::timestamptz, $2::bigint)
  AND ($3::text IS NULL OR a.hazard_type::text = $3)
  AND ($4::text IS NULL OR a.aoi_id = $4)
  AND a.level = ANY($5::text[])
ORDER BY a.dispatched_at, a.id
LIMIT $6
"""

# La riga precedente della stessa cella, pericolo e orizzonte: le righe dello
# sweep sono rade (#135, una a cambio di classe o al battito di 24 ore), quindi
# la precedente è la classe che la cella aveva fino a quel momento.
_TRANSIZIONI_SQL = """
SELECT r.id, r.computed_at AS t, r.cell_id, g.aoi_id, r.hazard_type::text AS hazard,
       r.class AS classe, r.score, r.measured, p.class AS prima, p.measured AS prima_misurata
FROM risk_assessments r
JOIN grid_cells g ON g.id = r.cell_id
LEFT JOIN LATERAL (
    SELECT q.class, q.measured
    FROM risk_assessments q
    WHERE q.cell_id = r.cell_id AND q.hazard_type = r.hazard_type AND q.horizon = r.horizon
      AND q.computed_at < r.computed_at
      AND q.computed_at >= r.computed_at - interval '14 days'
    ORDER BY q.computed_at DESC
    LIMIT 1
) p ON true
WHERE r.horizon = '24h'
  AND (r.computed_at, r.id) > ($1::timestamptz, $2::bigint)
  AND r.computed_at <= $3::timestamptz
  AND ($4::text IS NULL OR r.hazard_type::text = $4)
  AND ($5::text IS NULL OR g.aoi_id = $5)
  AND {predicato}
ORDER BY r.computed_at, r.id
LIMIT $6
"""

# Le corse previsionali girano ogni sei ore (02/08/14/20:20 UTC). La corsa
# precedente di una riga è quella da un'ora a nove ore prima: esclude la corsa
# stessa (che scrive in pochi minuti) e non salta a due corse fa. Se in quella
# finestra non c'è nessuna riga dello stesso pericolo e orizzonte, la corsa
# precedente non è girata e una cella senza riga non vuol dire «sotto
# Moderato»: niente evento.
_SALITE_SQL = """
WITH candidate AS MATERIALIZED (
    SELECT r.id, r.computed_at, r.cell_id, r.hazard_type, r.horizon, r.class, r.score
    FROM risk_assessments r
    WHERE r.horizon IN ('+24h', '+48h', '+72h')
      AND (r.computed_at, r.id) > ($1::timestamptz, $2::bigint)
      AND r.computed_at <= $3::timestamptz
      AND ($4::text IS NULL OR r.hazard_type::text = $4)
      AND r.class = ANY($7::text[])
)
SELECT c.id, c.computed_at AS t, c.cell_id, g.aoi_id, c.hazard_type::text AS hazard,
       c.class AS classe, c.score, c.horizon, p.class AS prima
FROM candidate c
JOIN grid_cells g ON g.id = c.cell_id
-- Una LATERAL con LIMIT e non un EXISTS: Postgres trasformava l'EXISTS in
-- un hash semi join su tutta la tabella (13 milioni di righe, oltre due minuti).
JOIN LATERAL (
    SELECT 1 FROM risk_assessments x
    WHERE x.hazard_type = c.hazard_type AND x.horizon = c.horizon
      AND x.computed_at BETWEEN c.computed_at - interval '9 hours'
                            AND c.computed_at - interval '1 hour'
    LIMIT 1
) corsa_prima ON true
LEFT JOIN LATERAL (
    SELECT q.class
    FROM risk_assessments q
    WHERE q.cell_id = c.cell_id AND q.hazard_type = c.hazard_type AND q.horizon = c.horizon
      AND q.computed_at BETWEEN c.computed_at - interval '9 hours'
                            AND c.computed_at - interval '1 hour'
    ORDER BY q.computed_at DESC
    LIMIT 1
) p ON true
WHERE ($5::text IS NULL OR g.aoi_id = $5)
  AND (p.class IS NULL OR NOT p.class = ANY($7::text[]))
ORDER BY c.computed_at, c.id
LIMIT $6
"""

_CAMBIO = (
    "p.class IS DISTINCT FROM r.class AND p.class IS NOT NULL"
    " AND (r.class = ANY($7::text[]) OR p.class = ANY($7::text[]))"
)
_NON_MISURATO = "r.measured IS FALSE AND p.measured IS DISTINCT FROM false"


async def _righe(nome: str, f: Filtro, dopo: Posizione, fino: datetime, limite: int) -> list[Any]:
    async with acquire() as conn:
        if nome == ALLERTA:
            assert f.livello_minimo is not None
            return list(
                await conn.fetch(
                    _ALLERTE_SQL,
                    dopo.t,
                    dopo.id,
                    f.hazard,
                    f.aoi_id,
                    livelli_da(f.livello_minimo),
                    limite,
                )
            )
        argomenti: list[Any] = [dopo.t, dopo.id, fino, f.hazard, f.aoi_id, limite]
        if nome == PREVISIONE:
            assert f.livello_minimo is not None
            argomenti.append(livelli_da(f.livello_minimo))
            return list(await conn.fetch(_SALITE_SQL, *argomenti))
        if nome == CAMBIO_CLASSE:
            assert f.livello_minimo is not None
            sql = _TRANSIZIONI_SQL.format(predicato=_CAMBIO)
            argomenti.append(livelli_da(f.livello_minimo))
        else:
            sql = _TRANSIZIONI_SQL.format(predicato=_NON_MISURATO)
        return list(await conn.fetch(sql, *argomenti))


async def poll(
    nome: str,
    argomenti: dict[str, Any] | None,
    cursore: str | None,
    *,
    max_age_ms: int | None = None,
    max_events: int | None = None,
    adesso: datetime | None = None,
) -> dict[str, Any]:
    """La risposta di ``events/poll`` per un abbonamento.

    Cursore ``None``: si parte da adesso, senza eventi. Un cursore più vecchio
    di ``max_age_ms`` (o della storia che il database tiene) riparte dal
    limite, e la risposta lo dice con ``truncated``.
    """
    f = filtro(nome, argomenti)
    ora = adesso or datetime.now(UTC)
    fino = ora if nome == ALLERTA else ora - MARGINE
    if cursore is None:
        return {
            "events": [],
            "cursor": codifica(Posizione(t=fino, id=0)),
            "truncated": False,
            "hasMore": False,
            "nextPollMs": PROSSIMA_RICHIESTA_MS,
        }
    dopo = decodifica(cursore)
    pavimento = ora - STORIA
    if max_age_ms is not None:
        pavimento = max(pavimento, ora - timedelta(milliseconds=max_age_ms))
    troncato = dopo.t is None or dopo.t < pavimento
    if troncato:
        dopo = Posizione(t=pavimento, id=0)
    limite = min(max_events or EVENTI_PREDEFINITI, EVENTI_MASSIMI)
    righe = await _righe(nome, f, dopo, fino, limite + 1)
    altre = len(righe) > limite
    righe = righe[:limite]
    if righe:
        ultima = righe[-1]
        nuovo = Posizione(t=ultima["t"], id=int(ultima["id"]))
    else:
        # Niente dopo il cursore fino al limite letto: si avanza fin lì, così
        # un abbonato in un periodo tranquillo non resta indietro.
        nuovo = dopo if nome == ALLERTA else Posizione(t=max(fino, dopo.t or fino), id=0)
    return {
        "events": [
            {
                "eventId": id_evento(nome, r),
                "name": nome,
                "timestamp": r["t"].astimezone(UTC).isoformat(),
                "data": payload(r, nome, r["t"].year),
            }
            for r in righe
        ],
        "cursor": codifica(nuovo),
        "truncated": troncato,
        "hasMore": altre,
        "nextPollMs": 0 if altre else PROSSIMA_RICHIESTA_MS,
    }


__all__ = ["EVENTI_MASSIMI", "MARGINE", "poll"]
