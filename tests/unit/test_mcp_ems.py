"""Gli strumenti MCP del registro EMS (#713): la stessa logica dell'API."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.core import ems_registro
from limen.mcp import tools


async def test_attivazione_sconosciuta_e_un_errore_non_un_vuoto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _nessuna(codice: str) -> None:
        return None

    monkeypatch.setattr(ems_registro, "registro", _nessuna)
    out = await tools.ems_registro_comuni(" emsr000 ")
    assert out == {"attivazione": "EMSR000", "error": "attivazione non in catalogo"}


async def test_registro_porta_attribuzione_e_avvertenza(monkeypatch: pytest.MonkeyPatch) -> None:
    riga = ems_registro.ComuneColpito(
        istat_code="039014",
        nome="Ravenna",
        aoi_id="it-emilia-romagna",
        acqua_km2=49.09,
        inizio=datetime(2023, 5, 16, tzinfo=UTC),
        osservato_dal=datetime(2023, 5, 18, tzinfo=UTC),
        osservato_al=datetime(2023, 5, 20, tzinfo=UTC),
        prodotti=("AOI01-GRA0",),
    )

    async def _una(codice: str) -> list[ems_registro.ComuneColpito]:
        return [riga]

    monkeypatch.setattr(ems_registro, "registro", _una)
    out = await tools.ems_registro_comuni("EMSR664")
    assert out["attivazione"] == "EMSR664"
    assert out["avvertenza"] == ems_registro.AVVERTENZA
    assert "2023" in out["attribuzione"]
    assert out["comuni"][0]["istat_code"] == "039014"
