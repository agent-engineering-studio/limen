"""B3 — deterministic briefing fidelity checks (pure)."""

from __future__ import annotations

from limen.agents.chat_agents.briefing_eval import (
    allowed_numbers_from_payload,
    evaluate_briefing,
)

_PAYLOAD = {"score": 0.62, "cells_high_or_above": 3, "analysis": {"confidence": 0.8}}
_OK_TEXT = ("La valutazione indica rischio alto con punteggio 0.62 e 3 celle critiche. " * 19)[:-1]


def test_faithful_briefing_passes() -> None:
    allowed = allowed_numbers_from_payload(_PAYLOAD)
    r = evaluate_briefing(_OK_TEXT, allowed_numbers=allowed)
    assert r.passed, r.violations
    assert 150 <= r.word_count <= 250


def test_invented_number_is_flagged() -> None:
    allowed = allowed_numbers_from_payload(_PAYLOAD)
    text = _OK_TEXT.replace("0.62", "0.91", 1)
    r = evaluate_briefing(text, allowed_numbers=allowed)
    assert not r.passed
    assert "0.91" in r.unknown_numbers


def test_length_alarm_terms_and_bullets_are_flagged() -> None:
    allowed = allowed_numbers_from_payload(_PAYLOAD)
    short = evaluate_briefing("Troppo corto.", allowed_numbers=allowed)
    assert any("lunghezza" in v for v in short.violations)
    bad = evaluate_briefing(
        _OK_TEXT + " Situazione di emergenza.\n- punto elenco",
        allowed_numbers=allowed,
    )
    assert any("emergenza" in v for v in bad.violations)
    assert any("elenchi" in v for v in bad.violations)


def test_comma_decimals_and_structural_numbers_allowed() -> None:
    allowed = allowed_numbers_from_payload(_PAYLOAD)
    text = ("Il punteggio 0,62 richiede monitoraggio nelle prossime 48 ore su 3 celle. " * 16)[:-1]
    r = evaluate_briefing(text, allowed_numbers=allowed)
    assert r.passed, r.violations
