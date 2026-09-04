"""Parametro hazard su legenda, MCP e A2A (issue #86).

Qui sta ciò che si verifica senza database. Le superfici HTTP che leggono
`risk_assessments` sono in `tests/integration/test_hazard_api.py`.

Il criterio di #57 è la **retrocompatibilità**: senza il parametro ogni
superficie si comporta come prima.
"""

from __future__ import annotations

import pytest
from fastapi import Response

from limen.api.endpoints.risk import legend
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.scoring.regional_thresholds import load_hazard_thresholds
from limen.mcp import tools


# ---------------------------------------------------------------------------
# Legenda: soglie per pericolo
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_legend_without_the_parameter_matches_the_default() -> None:
    """Il cuore della retrocompatibilità: omettere il parametro deve dare la
    stessa risposta del pericolo di default esplicito."""
    assert await legend(Response()) == await legend(Response(), DEFAULT_HAZARD)


@pytest.mark.asyncio
async def test_legend_reads_the_requested_hazard_thresholds() -> None:
    """Le soglie di classe sono per pericolo da #84: una legenda costruita
    dal file delle frane etichetterebbe male i colori di un altro pericolo."""
    payload = await legend(Response(), DEFAULT_HAZARD)
    t = load_hazard_thresholds(DEFAULT_HAZARD)
    assert payload["model"]["weights"]["static"] == t.weights.static


@pytest.mark.asyncio
async def test_legend_of_an_unconfigured_hazard_is_a_404() -> None:
    """Il nome è valido nell'enum ma questo deployment non lo configura: è una
    risorsa che non c'è, non un guasto del server. Meglio così che colori
    sbagliati presentati come giusti."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await legend(Response(), HazardType.WILDFIRE)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# MCP: confine esterno, quindi la validazione ci sta
# ---------------------------------------------------------------------------
def test_mcp_coerces_a_known_hazard() -> None:
    assert tools._coerce_hazard(None) is DEFAULT_HAZARD
    assert tools._coerce_hazard("flood") is HazardType.FLOOD


def test_mcp_rejects_an_unknown_hazard_naming_the_valid_ones() -> None:
    """Un agente che sbaglia il nome deve leggere cosa è valido, non ottenere
    di nascosto le frane etichettate come altro."""
    with pytest.raises(ValueError, match="unknown hazard") as exc:
        tools._coerce_hazard("pippo")
    assert "landslide" in str(exc.value)


def test_comune_tools_refuse_a_hazard_they_cannot_honour() -> None:
    """`mv_comune_risk` è fissata sul pericolo di default in SQL, perché il suo
    `exposure_rank` legge una chiave che solo il breakdown delle frane ha.
    Accettare e ignorare il parametro farebbe credere all'agente di aver
    ottenuto numeri sull'alluvione."""
    assert tools._require_default_hazard(None, "top_comuni") is DEFAULT_HAZARD
    with pytest.raises(ValueError, match="only"):
        tools._require_default_hazard("flood", "top_comuni")


# ---------------------------------------------------------------------------
# A2A: la Agent Card deve restare veritiera
# ---------------------------------------------------------------------------
def test_a2a_skills_declare_the_hazard_parameter() -> None:
    """Una skill il cui handler accetta 'hazard' deve dirlo nella descrizione:
    è l'unico posto in cui un agente scopre i parametri."""
    from limen.a2a.skills import SKILLS

    for skill_id in ("risk_summary", "top_risk_cells", "cell_breakdown", "recent_alerts"):
        assert "hazard" in SKILLS[skill_id].description, skill_id


def test_a2a_comune_skills_do_not_promise_a_hazard() -> None:
    """Le due skill sui comuni non possono onorarlo, quindi non devono
    annunciarlo: una Agent Card che promette più di quanto mantiene è peggio
    di una che tace."""
    from limen.a2a.skills import SKILLS

    for skill_id in ("top_comuni", "comune_risk"):
        assert "hazard" not in SKILLS[skill_id].description, skill_id


# ---------------------------------------------------------------------------
# La superficie MCP deve esporre davvero il parametro
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mcp_wrappers_expose_the_hazard_parameter() -> None:
    """I wrapper `@mcp.tool()` sono il confine che un agente vede.

    Aggiungere il parametro in `mcp/tools.py` senza toccarli lo renderebbe
    irraggiungibile, e nulla lo segnalerebbe: le due firme possono divergere
    in silenzio perché il wrapper chiama per nome.
    """
    fastmcp = pytest.importorskip("fastmcp")
    assert fastmcp  # usato solo come gate di disponibilità

    from limen.mcp.server import _build_server

    listed = await _build_server()._list_tools()
    params = {t.name: set((t.parameters or {}).get("properties", {})) for t in listed}

    for name in (
        "tool_risk_summary",
        "tool_top_risk_cells",
        "tool_cell_breakdown",
        "tool_recent_alerts",
        "tool_run_monitor",
        "tool_forecast_history",
    ):
        assert "hazard" in params[name], name

    # I due sui comuni lo accettano per poterlo rifiutare con una ragione,
    # invece di lasciarlo cadere come farebbe un parametro ignoto.
    assert "hazard" in params["tool_top_comuni"]
    assert "hazard" in params["tool_comune_risk"]

    # E il tool che dice quali pericoli chiedere esiste, perché le istruzioni
    # del server dicono all'agente di chiamarlo per primo.
    assert "tool_hazards" in params


def test_mcp_instructions_document_the_parameter() -> None:
    """Le istruzioni sono l'unico posto dove un agente legge le firme."""
    from limen.mcp.server import SERVER_INSTRUCTIONS

    assert "hazard?" in SERVER_INSTRUCTIONS
    assert "hazards()" in SERVER_INSTRUCTIONS
    # E dichiara il limite dei comuni, invece di lasciarlo scoprire a un errore.
    assert "Landslide only" in SERVER_INSTRUCTIONS
