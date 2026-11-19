"""Il resoconto radar di un evento verificato (#643): uno o due giorni UTC."""

from __future__ import annotations

from datetime import UTC, date, datetime

from limen.cli.resoconto_radar import giorni_dell_evento


def test_un_evento_a_meta_giornata_ha_un_giorno() -> None:
    assert giorni_dell_evento(datetime(2026, 11, 7, 15, 30, tzinfo=UTC), "T1") == [
        date(2026, 11, 7)
    ]


def test_un_evento_all_una_di_notte_ha_anche_il_giorno_prima() -> None:
    assert giorni_dell_evento(datetime(2026, 10, 10, 1, 0, tzinfo=UTC), "T1") == [
        date(2026, 10, 9),
        date(2026, 10, 10),
    ]


def test_un_evento_a_tarda_sera_ha_anche_il_giorno_dopo() -> None:
    assert giorni_dell_evento(datetime(2026, 10, 10, 21, 0, tzinfo=UTC), "T2") == [
        date(2026, 10, 10),
        date(2026, 10, 11),
    ]


def test_con_l_ora_ignota_resta_il_giorno() -> None:
    assert giorni_dell_evento(datetime(2026, 11, 10, 1, 0, tzinfo=UTC), "T3") == [
        date(2026, 11, 10)
    ]
