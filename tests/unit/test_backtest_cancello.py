"""``LIMEN_BACKTEST_CANCELLO_INNESCO`` (#656)."""

from __future__ import annotations

import pytest

from limen.cli.backtest import cancello_da_env


def test_cancello_da_env() -> None:
    assert cancello_da_env("") is None
    solo = cancello_da_env("0.34")
    assert solo is not None and (solo.soglia, solo.tetto) == (0.0, 0.34)
    due = cancello_da_env(" 0.2:0.34 ")
    assert due is not None and (due.soglia, due.tetto) == (0.2, 0.34)
    for sbagliato in ("x", "0.2:0.3:0.4", "1.5", "1:0.3"):
        with pytest.raises(ValueError):
            cancello_da_env(sbagliato)
