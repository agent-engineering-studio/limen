"""The /api/legend model card must mirror regional_thresholds.yaml exactly.

The public "Il modello, spiegato" page (issue #16) draws its charts from this
payload, so the endpoint is the single source of truth — no numbers are
hard-coded in the frontend. This guards against drift between the two.
"""

from __future__ import annotations

import pytest
from fastapi import Response

from limen.api.endpoints.risk import legend
from limen.core.scoring.regional_thresholds import load_regional_thresholds


@pytest.mark.asyncio
async def test_legend_model_card_matches_yaml() -> None:
    payload = await legend(Response())
    t = load_regional_thresholds()
    model = payload["model"]

    assert model["weights"] == {
        "static": t.weights.static,
        "meteo": t.weights.meteo,
        "seismic": t.weights.seismic,
        "fire": t.weights.fire,
        "hydrology": t.weights.hydrology,
    }
    assert model["meteo_weights"]["caine"] == t.meteo.weights.caine
    assert model["api"]["sigmoid_sigma_mm"] == t.api.sigmoid_sigma_mm
    assert model["soil"]["sigmoid_center"] == t.soil.sigmoid_center
    assert model["seismic"]["tau_days"] == t.seismic.tau_days
    assert model["post_fire"]["peak_months"] == t.post_fire.peak_months
    assert model["caine"]["macroregions"]["italy_default"] == {
        "alpha": t.caine.macroregions["italy_default"].alpha,
        "beta": t.caine.macroregions["italy_default"].beta,
    }


@pytest.mark.asyncio
async def test_legend_still_exposes_five_classes() -> None:
    payload = await legend(Response())
    assert [c["level"] for c in payload["classes"]] == [
        "None",
        "Low",
        "Moderate",
        "High",
        "VeryHigh",
    ]
