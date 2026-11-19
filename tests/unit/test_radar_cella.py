"""Il radar visto dalla cella (#643): affidabilità e rarità, un'etichetta fuori dal punteggio."""

from __future__ import annotations

from limen.core.models.hazard import HazardType
from limen.integrations.dpc.cella import pioggia_osservata, radar_della_cella

_MELITO = (15.78, 37.92)
_LIPARI = (14.95, 38.47)


def test_a_lipari_il_radar_non_e_affidabile() -> None:
    r = radar_della_cella(*_LIPARI, HazardType.LANDSLIDE, {})
    assert r.affidabile is False
    assert r.pioggia_mm is None and r.ritorno_anni is None


def test_la_pioggia_di_melito_e_rara_li() -> None:
    r = radar_della_cella(*_MELITO, HazardType.FLOOD, {"rain_observed_mm": 180.0})
    assert r.affidabile is True
    assert r.finestra_ore == 24
    assert r.ritorno_anni is not None and r.ritorno_anni >= 20
    assert r.anni_di_dati == 8


def test_la_rarita_solo_per_l_alluvione_e_con_pioggia() -> None:
    assert pioggia_osservata(HazardType.WILDFIRE, {"rain_observed_mm": 30.0}) is None
    assert pioggia_osservata(HazardType.FLOOD, {}) is None
    secco = radar_della_cella(*_MELITO, HazardType.FLOOD, {"rain_observed_mm": 0.0})
    assert secco.ritorno_anni is None and secco.finestra_ore is None


def test_fuori_dalla_mappa_non_si_sa() -> None:
    assert radar_della_cella(0.0, 60.0, HazardType.FLOOD, {}).affidabile is None
