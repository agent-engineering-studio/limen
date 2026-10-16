"""Quali ore rifà il job di rollup (#252, rilievo sulla PR #268)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from limen.api.jobs.iot_rollup import ore_da_rifare

CODA = timedelta(minutes=25)
ORA = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def test_a_inizio_ora_rifa_anche_la_precedente() -> None:
    """La misura delle 11:55 arrivata alle 12:05 è in tempo reale: il giro
    delle 12:05 deve rifare le 11:00, o non entra in nessun rollup."""
    assert ore_da_rifare(ORA + timedelta(minutes=5), coda=CODA) == [
        ORA - timedelta(hours=1),
        ORA,
    ]


def test_passata_la_coda_solo_l_ora_in_corso() -> None:
    assert ore_da_rifare(ORA + timedelta(minutes=25), coda=CODA) == [ORA]
    assert ore_da_rifare(ORA + timedelta(minutes=59), coda=CODA) == [ORA]
