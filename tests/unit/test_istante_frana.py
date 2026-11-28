"""L'istante di una frana datata: la regola di tutte le librerie (ispra-idrogeo 0.15)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from limen.core.istante_frana import istante_frana

_ROMA_INVERNO = timezone(timedelta(hours=1))


def test_con_l_ora_resta_quella() -> None:
    t = datetime(2020, 10, 3, 12, 30, tzinfo=UTC)
    assert istante_frana(t, True) == t


def test_senza_ora_la_fine_del_giorno_a_roma_qualunque_momento_sia_salvato() -> None:
    fine = datetime(2020, 10, 3, 22, 0, tzinfo=UTC)  # mezzanotte del 4 a Roma, ora legale
    for salvato in (
        datetime(2020, 10, 3, 10, 0, tzinfo=UTC),  # mezzogiorno di Roma (FraneItalia)
        datetime(2020, 10, 2, 22, 0, tzinfo=UTC),  # la mezzanotte locale (e-ITALICA)
        datetime(2020, 10, 3, 18, 0, tzinfo=UTC),  # le 20 di una data convenzionale
    ):
        assert istante_frana(salvato, False) == fine
    # in inverno è un'ora dopo
    assert istante_frana(datetime(2020, 12, 27, 12, tzinfo=_ROMA_INVERNO), False) == datetime(
        2020, 12, 27, 23, 0, tzinfo=UTC
    )


def test_il_giorno_del_cambio_d_ora_non_e_di_24_ore() -> None:
    # il 25 ottobre 2020 a Roma dura 25 ore: la sua fine è la mezzanotte del 26
    salvato = datetime(2020, 10, 25, 11, 0, tzinfo=UTC)
    assert istante_frana(salvato, False) == datetime(2020, 10, 25, 23, 0, tzinfo=UTC)
    # il 29 marzo 2020 dura 23 ore
    salvato = datetime(2020, 3, 29, 10, 0, tzinfo=UTC)
    assert istante_frana(salvato, False) == datetime(2020, 3, 29, 22, 0, tzinfo=UTC)
