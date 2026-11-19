"""Il catalogo radar delle piogge rare (#643): candidati per la raccolta, mai punteggi."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from limen.integrations.dpc.piogge_rare import piogge_rare_del_giorno


def test_senza_fotogrammi_non_ci_sono_eventi(tmp_path: Path) -> None:
    assert piogge_rare_del_giorno(tmp_path, date(2026, 10, 10)) == []
