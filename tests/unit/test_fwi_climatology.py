"""Com'è di solito l'FWI (#155, opzione C).

La classe assoluta dice «High» a FWI 36 in agosto come in ottobre. La
climatologia dice dove cade quel valore fra i giorni dello stesso mese nello
stesso punto: questi test fissano le due funzioni pure che lo calcolano e il
passo della catena che riempie la distribuzione.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import pytest

from limen.cli.fwi_backfill import params_from
from limen.cli.fwi_climatology import _AVVIAMENTO, accumula, copertura_valida
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds
from limen.core.scoring.wildfire.climatology import LIVELLI, percentile, quantili
from limen.integrations.openmeteo.dtos import FireWeatherObservation


def test_i_quantili_sono_ventuno_e_vanno_dal_minimo_al_massimo() -> None:
    q = quantili([float(v) for v in range(101)])
    assert len(q) == len(LIVELLI) == 21
    assert q[0] == 0.0 and q[10] == 50.0 and q[-1] == 100.0


def test_il_percentile_si_interpola_fra_i_quantili() -> None:
    q = quantili([float(v) for v in range(101)])
    assert percentile(36.0, q) == pytest.approx(36.0)
    assert percentile(-1.0, q) == 0.0
    assert percentile(500.0, q) == 100.0


def test_su_un_tratto_piatto_prende_il_centro() -> None:
    # Metà dei giorni a FWI 0, come d'inverno: uno zero non è né il minimo
    # assoluto né la mediana, è «come la metà dei giorni».
    q = quantili([0.0] * 50 + [float(v) for v in range(1, 51)])
    assert 20.0 <= percentile(0.0, q) <= 30.0


def test_la_catena_scarta_l_avviamento_e_mette_ogni_giorno_nel_suo_mese() -> None:
    soglie = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(soglie, WildfireThresholds)
    params = params_from(soglie)
    inizio = date(2020, 7, 1)
    giorni = [inizio + timedelta(days=i) for i in range(90)]
    secco = {
        g: FireWeatherObservation(
            day=g,
            temperature_c=30.0,
            relative_humidity_pct=30.0,
            wind_speed_kmh=15.0,
            rain_24h_mm=0.0,
        )
        for g in giorni
    }
    # Un giorno senza dato: si salta, non diventa un giorno di essiccazione.
    del secco[giorni[70]]
    per_mese: dict[int, list[float]] = defaultdict(list)
    _, avviati = accumula(secco, giorni, params, params.initial_state, 0, per_mese)
    assert avviati == 89
    assert sum(len(v) for v in per_mese.values()) == 89 - _AVVIAMENTO
    assert set(per_mese) == {8, 9}


def test_un_anno_bucato_non_entra_nella_distribuzione() -> None:
    # Una richiesta degradata restituisce una serie vuota: senza questo
    # controllo la catena attraverserebbe il buco come giorni consecutivi.
    giorni = [date(2020, 1, 1) + timedelta(days=i) for i in range(366)]
    assert copertura_valida(giorni, giorni, max_buco=5)
    assert not copertura_valida([], giorni, max_buco=5)
    # Il 97 % dei giorni, ma con un buco di otto: la catena non lo sopporta.
    bucato = giorni[:100] + giorni[108:]
    assert len(bucato) >= 0.95 * len(giorni)
    assert not copertura_valida(bucato, giorni, max_buco=5)
    assert copertura_valida(giorni[:100] + giorni[103:], giorni, max_buco=5)
