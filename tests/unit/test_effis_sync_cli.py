"""`limen effis-sync` rifiuta una finestra che non ha senso (Codex, #292)."""

from __future__ import annotations

import pytest

from limen.cli import effis_sync


@pytest.mark.parametrize("valore", ["-1", "0", "tanti"])
async def test_giorni_non_validi_non_toccano_niente(
    monkeypatch: pytest.MonkeyPatch, valore: str
) -> None:
    def vietato(*a: object, **k: object) -> None:
        raise AssertionError("non deve aprire il database")

    monkeypatch.setenv("LIMEN_EFFIS_GIORNI", valore)
    monkeypatch.setattr(effis_sync, "lifespan_pool", vietato)
    assert await effis_sync.run() == 1
