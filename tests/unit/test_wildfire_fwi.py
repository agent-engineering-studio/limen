"""La catena FWI vista da Limen (issue #61).

Le equazioni di Van Wagner vivono nel pacchetto `fwi-chain`, con la loro
suite (il giorno di riferimento a 1e-9, i rami della pioggia, i limiti
fisici). Qui resta ciò che è di Limen: i parametri che arrivano dal
`wildfire.yaml` e il reticolo dei nodi su cui le catene sono persistite.
"""

from __future__ import annotations

import pytest
from fwi_chain import STANDARD_PARAMS, FwiParams, advance

from limen.cli.fwi_backfill import params_from
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds


def _yaml_params() -> FwiParams:
    thresholds = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(thresholds, WildfireThresholds)
    return params_from(thresholds)


def test_the_yaml_declares_van_wagners_standard_params() -> None:
    """Il YAML porta i valori pubblicati: una tabella di lunghezza del giorno
    toccata per sbaglio sposterebbe ogni catena d'Italia senza un errore."""
    assert _yaml_params() == STANDARD_PARAMS


def test_the_yaml_params_reproduce_the_reference_day() -> None:
    """L'adattatore YAML → `FwiParams` non perde niente per strada."""
    params = _yaml_params()
    out = advance(
        params.initial_state,
        month=4,
        temperature_c=17.0,
        relative_humidity_pct=42.0,
        wind_speed_kmh=25.0,
        rain_24h_mm=0.0,
        params=params,
    )
    assert out.fwi == pytest.approx(10.096371392382, abs=1e-9)


# ---------------------------------------------------------------------------
# Il reticolo dei nodi — l'identità di una catena persistita
# ---------------------------------------------------------------------------
def test_the_snapped_grid_is_shared_between_overlapping_areas() -> None:
    """Una catena FWI vive settimane, quindi l'identità del suo nodo non può
    dipendere da dove passa il confine di un'AOI.

    `build_rain_nodes` ancora al bbox, che va bene per un campione di pioggia
    che esiste solo per quella chiamata. Per qualcosa di persistito no: due
    AOI sovrapposte avrebbero reticoli diversi, e ridisegnare un confine
    orfanerebbe ogni catena facendo ripartire la ricorsione in silenzio.
    """
    from limen.integrations.openmeteo.grid import build_rain_nodes, build_snapped_nodes

    spacing = 0.25
    a = set(build_snapped_nodes((15.33, 39.90, 16.90, 40.90), spacing=spacing))
    b = set(build_snapped_nodes((15.40, 40.00, 17.10, 41.20), spacing=spacing))
    assert a & b, "due AOI sovrapposte devono condividere i nodi"
    for lon, lat in a | b:
        assert lon / spacing == pytest.approx(round(lon / spacing))
        assert lat / spacing == pytest.approx(round(lat / spacing))

    # Il reticolo della pioggia resta ancorato al bbox: cambiarlo sposterebbe
    # i campioni di precipitazione e con essi i punteggi frana.
    assert build_rain_nodes((15.33, 39.90, 16.90, 40.90), spacing=spacing)[0] == (15.33, 39.90)


def test_snapped_node_coordinates_do_not_drift() -> None:
    """Un accumulatore float produce 40.99999999999999, che come chiave è un
    nodo diverso: le coordinate si ottengono moltiplicando l'indice del passo."""
    from limen.integrations.openmeteo.grid import build_snapped_nodes

    nodes = build_snapped_nodes((15.0, 40.0, 18.0, 43.0), spacing=0.25)
    assert (16.0, 41.0) in nodes
    assert (17.5, 42.5) in nodes
