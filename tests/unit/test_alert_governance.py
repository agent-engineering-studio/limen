"""Governo degli alert: rollup comunale, rate limiting, digest (issue #59).

Le proprietà che l'acceptance criteria mette alla prova sono decidibili senza
I/O, quindi si provano qui: 5.000 celle sopra soglia devono uscire come poche
decine di messaggi, la classe massima non deve mai finire in coda, e il testo
del digest deve dire quali comuni hanno più di un pericolo insieme.
"""

from __future__ import annotations

from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel
from limen.notifications.governance import (
    UNKNOWN_COMUNE_LABEL,
    ComuneAggregate,
    aggregate_by_comune,
    rate_limit_verdict,
    summarise_comuni_it,
    summarise_digest_it,
    worst_level,
)
from tests.factories import landslide_record


def _cells(
    n: int, *, comune_ogni: int, level: RiskLevel = RiskLevel.High, base_score: float = 0.60
) -> tuple[list[tuple[object, float]], dict[str, str], dict[str, str]]:
    """``n`` celle distribuite su ``n / comune_ogni`` comuni."""
    prioritised = []
    istat: dict[str, str] = {}
    nomi: dict[str, str] = {}
    for i in range(n):
        cell_id = f"aoi|{i // 100}|{i % 100}"
        code = f"0{16000 + i // comune_ogni}"
        # Punteggio decrescente: l'executor consegna già ordinato per priorità.
        score = min(0.99, base_score + (n - i) / (n * 50))
        prioritised.append((landslide_record(cell_id, score=score, level=level, s=0.7), score))
        istat[cell_id] = code
        nomi[code] = f"Comune {code}"
    return prioritised, nomi, istat


# --- rollup comunale --------------------------------------------------------


def test_five_thousand_cells_collapse_into_one_message_per_comune() -> None:
    """Il criterio di accettazione: 5k celle ⇒ messaggi entro i limiti.

    Il rollup è ciò che rende il rate limit sostenibile: senza, un fronte
    esteso sarebbe migliaia di avvisi e nessun limite orario potrebbe farci
    stare l'informazione.
    """
    prioritised, nomi, istat = _cells(5000, comune_ogni=50)
    aggregates = aggregate_by_comune(
        prioritised, comuni=nomi, istat_codes=istat, aoi_id="it-puglia", hazard=HazardType.LANDSLIDE
    )
    assert len(aggregates) == 100
    assert sum(a.cells_count for a in aggregates) == 5000
    # Un messaggio, non uno per comune: il payload li porta tutti insieme.
    assert len(summarise_comuni_it(aggregates)) > 0


def test_aggregates_are_ordered_by_severity_then_deterministically() -> None:
    prioritised, nomi, istat = _cells(30, comune_ogni=10)
    # Alza una cella a VeryHigh in un comune che non è il primo per punteggio.
    record = landslide_record("aoi|9|9", score=0.9, level=RiskLevel.VeryHigh, s=0.8)
    istat["aoi|9|9"] = "099999"
    nomi["099999"] = "Zzz Ultimo"
    prioritised.append((record, 0.9))

    aggregates = aggregate_by_comune(
        prioritised, comuni=nomi, istat_codes=istat, aoi_id="it-puglia", hazard=HazardType.LANDSLIDE
    )
    # La classe viene prima del punteggio: VeryHigh guida anche se il nome
    # finisce per ultimo in alfabeto.
    assert aggregates[0].comune == "Zzz Ultimo"
    assert aggregates[0].max_level is RiskLevel.VeryHigh
    # Stesso input ⇒ stesso ordine.
    again = aggregate_by_comune(
        prioritised, comuni=nomi, istat_codes=istat, aoi_id="it-puglia", hazard=HazardType.LANDSLIDE
    )
    assert [a.comune for a in again] == [a.comune for a in aggregates]


def test_cells_without_a_comune_are_named_not_dropped() -> None:
    """Una cella non taggata esiste: sparirebbe da un rollup che la ignora."""
    prioritised, nomi, istat = _cells(10, comune_ogni=10)
    orfana = landslide_record("aoi|7|7", score=0.7, level=RiskLevel.High, s=0.7)
    prioritised.append((orfana, 0.7))  # nessuna voce in `istat`

    aggregates = aggregate_by_comune(
        prioritised, comuni=nomi, istat_codes=istat, aoi_id="it-puglia", hazard=HazardType.LANDSLIDE
    )
    assert sum(a.cells_count for a in aggregates) == 11
    orfani = [a for a in aggregates if a.istat_code is None]
    assert len(orfani) == 1
    assert orfani[0].label == UNKNOWN_COMUNE_LABEL


def test_top_cells_are_capped_but_the_count_is_not() -> None:
    prioritised, nomi, istat = _cells(200, comune_ogni=200)
    aggregates = aggregate_by_comune(
        prioritised, comuni=nomi, istat_codes=istat, aoi_id="it-puglia", hazard=HazardType.LANDSLIDE
    )
    assert len(aggregates) == 1
    assert aggregates[0].cells_count == 200
    # Le celle nominate sono poche; il conteggio resta quello vero.
    assert len(aggregates[0].top_cells) == 3


# --- rate limiting ----------------------------------------------------------


def test_under_the_limit_sends() -> None:
    assert (
        rate_limit_verdict(
            sends_last_hour=2,
            max_per_hour=6,
            level=RiskLevel.High,
            bypass_level=RiskLevel.VeryHigh,
        )
        == "send"
    )


def test_over_the_limit_queues() -> None:
    assert (
        rate_limit_verdict(
            sends_last_hour=6,
            max_per_hour=6,
            level=RiskLevel.High,
            bypass_level=RiskLevel.VeryHigh,
        )
        == "queue"
    )


def test_very_high_is_never_delayed_by_the_digest() -> None:
    """Criterio di accettazione: la gravità non entra mai in coda.

    Il digest protegge l'attenzione; trattenere l'allerta peggiore per
    proteggere l'attenzione ha invertito lo scopo del limite.
    """
    for carico in (6, 60, 600):
        assert (
            rate_limit_verdict(
                sends_last_hour=carico,
                max_per_hour=6,
                level=RiskLevel.VeryHigh,
                bypass_level=RiskLevel.VeryHigh,
            )
            == "send"
        )


def test_zero_limit_means_no_limit_not_silence() -> None:
    """Nessun operatore scrive 0 per dire «non spedire mai»."""
    assert (
        rate_limit_verdict(
            sends_last_hour=999,
            max_per_hour=0,
            level=RiskLevel.Moderate,
            bypass_level=RiskLevel.VeryHigh,
        )
        == "send"
    )


def test_disabled_governance_always_sends() -> None:
    assert (
        rate_limit_verdict(
            sends_last_hour=999,
            max_per_hour=1,
            level=RiskLevel.Low,
            bypass_level=RiskLevel.VeryHigh,
            enabled=False,
        )
        == "send"
    )


# --- testi ------------------------------------------------------------------


def _agg(
    comune: str,
    hazard: HazardType,
    level: RiskLevel,
    *,
    cells: int = 3,
    score: float = 0.7,
) -> ComuneAggregate:
    return ComuneAggregate(
        istat_code=comune[:6],
        comune=comune,
        aoi_id="it-puglia",
        hazard=hazard,
        max_level=level,
        max_score=score,
        cells_count=cells,
        top_cells=(("aoi|0|0", score, level),),
    )


def test_comune_summary_names_comuni_not_cell_ids() -> None:
    testo = summarise_comuni_it(
        [
            _agg("Altamura", HazardType.LANDSLIDE, RiskLevel.High, cells=12, score=0.78),
            _agg("Gravina", HazardType.LANDSLIDE, RiskLevel.Moderate, cells=1, score=0.42),
        ]
    )
    assert "Altamura: 12 aree" in testo
    assert "Gravina: 1 area" in testo  # singolare, non "1 aree"
    assert "livello alto" in testo
    assert "13 aree" in testo
    assert "aoi|0|0" not in testo


def test_comune_summary_truncates_the_list_but_says_how_many_are_left() -> None:
    molti = [
        _agg(f"Comune {i}", HazardType.FLOOD, RiskLevel.High, cells=2, score=0.6) for i in range(9)
    ]
    testo = summarise_comuni_it(molti, max_comuni=5)
    assert "e altri 4 comuni" in testo
    assert "in 9 comuni" in testo


def test_digest_marks_the_comuni_with_more_than_one_hazard() -> None:
    """È l'alert congiunto della #58: due pericoli, un messaggio.

    Il workflow è per pericolo, quindi frana e alluvione sullo stesso comune
    nascono in due esecuzioni che non si conoscono. La coda del digest le
    ritrova insieme.
    """
    testo = summarise_digest_it(
        [
            _agg("Matera", HazardType.LANDSLIDE, RiskLevel.High, cells=4, score=0.72),
            _agg("Matera", HazardType.FLOOD, RiskLevel.High, cells=2, score=0.68),
            _agg("Potenza", HazardType.WILDFIRE, RiskLevel.Moderate, cells=7, score=0.44),
        ]
    )
    assert "Matera" in testo and "Potenza" in testo
    assert "frana alto (4)" in testo
    assert "alluvione alto (2)" in testo
    # La marca esiste solo dove i pericoli sono più di uno.
    matera = next(r for r in testo.splitlines() if r.startswith("· Matera"))
    potenza = next(r for r in testo.splitlines() if r.startswith("· Potenza"))
    assert "più pericoli insieme" in matera
    assert "più pericoli insieme" not in potenza


def test_digest_orders_comuni_by_worst_level() -> None:
    testo = summarise_digest_it(
        [
            _agg("Basso", HazardType.FLOOD, RiskLevel.Moderate, score=0.40),
            _agg("Alto", HazardType.FLOOD, RiskLevel.VeryHigh, score=0.90),
        ]
    )
    righe = [r for r in testo.splitlines() if r.startswith("·")]
    assert righe[0].startswith("· Alto")
    assert "livello massimo molto alto" in testo


def test_empty_inputs_produce_empty_text() -> None:
    """Nessun aggregato non è «zero allerte»: è niente da dire."""
    assert summarise_comuni_it([]) == ""
    assert summarise_digest_it([]) == ""
    assert worst_level([]) is RiskLevel.None_


# --- protocollo FAR ---------------------------------------------------------


def test_review_markdown_has_a_row_per_alert_and_an_empty_verdict_column() -> None:
    from datetime import UTC, datetime

    from limen.cli.review_alerts import render_review_markdown

    righe = [
        {
            "id": 1,
            "istat_code": "016001",
            "comune": "Altamura",
            "aoi_id": "it-puglia",
            "hazard_type": "landslide",
            "max_level": "High",
            "max_score": 0.78,
            "cells_count": 12,
            "top_cells": [{"cell_id": "it-puglia|1|1", "score": 0.78, "level": "High"}],
            "state": "sent",
            "created_at": datetime(2026, 9, 1, 6, 30, tzinfo=UTC),
            "sent_at": None,
            "digest_id": None,
        }
    ]
    md = render_review_markdown(righe, days=30, generated_at=datetime(2026, 9, 8, 7, 0, tzinfo=UTC))
    assert "| 1 | 01/09 06:30 | Altamura | frana | alto | 12 | 0.78 |  |  |" in md
    assert "non verificabile" in md
    # Il denominatore va nominato: un tasso senza di esso non è difendibile.
    assert "falsi positivi / (confermati + falsi positivi)" in md
    assert "it-puglia|1|1" in md


def test_review_markdown_says_so_when_there_is_nothing_to_verify() -> None:
    from datetime import UTC, datetime

    from limen.cli.review_alerts import render_review_markdown

    md = render_review_markdown([], days=7, generated_at=datetime(2026, 9, 8, tzinfo=UTC))
    assert "Nessuna allerta nella finestra richiesta" in md
    assert "|---|" not in md


def test_ten_cycles_with_a_limit_of_six_send_six_and_queue_the_rest() -> None:
    """Il criterio di accettazione, sulla sequenza: i messaggi stanno nel limite.

    Simula dieci cicli consecutivi con lo stesso limite: il contatore orario
    cresce solo sugli invii, quindi dal settimo in poi il verdetto è coda. È
    ciò che rende leggibile un fronte che dura tutta la notte.
    """
    max_per_hour = 6
    inviati = 0
    accodati = 0
    for _ in range(10):
        verdetto = rate_limit_verdict(
            sends_last_hour=inviati,
            max_per_hour=max_per_hour,
            level=RiskLevel.High,
            bypass_level=RiskLevel.VeryHigh,
        )
        if verdetto == "send":
            inviati += 1
        else:
            accodati += 1
    assert inviati == max_per_hour
    assert accodati == 4


def test_a_very_high_cycle_gets_through_a_saturated_hour() -> None:
    """Dieci cicli High saturano il limite; l'undicesimo, VeryHigh, esce."""
    inviati = 0
    for _ in range(10):
        if (
            rate_limit_verdict(
                sends_last_hour=inviati,
                max_per_hour=6,
                level=RiskLevel.High,
                bypass_level=RiskLevel.VeryHigh,
            )
            == "send"
        ):
            inviati += 1
    assert inviati == 6
    assert (
        rate_limit_verdict(
            sends_last_hour=inviati,
            max_per_hour=6,
            level=RiskLevel.VeryHigh,
            bypass_level=RiskLevel.VeryHigh,
        )
        == "send"
    )
