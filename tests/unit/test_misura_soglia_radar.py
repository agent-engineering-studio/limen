"""Misura #677: punteggio sulla curva, momenti ordinari, frane di e-ITALICA."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from rainfall_thresholds import ITALICA_T5

from limen.cli.misura_soglia_radar import (
    _BASE,
    SENZA_EVENTO,
    blocco,
    frane_italica,
    indice,
    istanti_ordinari,
    punteggio,
    sulla_stessa_durata,
)

_SOGLIA = ITALICA_T5["northern"]


def _serie(ore: int = 1000) -> np.ndarray:
    return np.zeros(ore, dtype=np.float32)


def _punteggio(serie: np.ndarray, e: int, fattore: float = 1.0):  # type: ignore[no-untyped-def]
    return punteggio(serie, e, _SOGLIA, pausa_ore=6, minimo_mm=2.0, fattore=fattore)


def test_l_indice_e_l_ultima_ora_finita() -> None:
    assert indice(_BASE + timedelta(hours=1)) == 0
    assert indice(_BASE + timedelta(hours=1, minutes=59)) == 0
    assert indice(_BASE + timedelta(hours=2)) == 1


def test_un_nubifragio_nelle_48_ore_sta_sopra_la_curva() -> None:
    serie = _serie()
    serie[590:596] = 20.0  # 120 mm in 6 ore, finite 5 ore prima
    eccesso, durata, mm = _punteggio(serie, 600)
    assert (durata, mm) == (6.0, 120.0)
    assert eccesso is not None and eccesso > 0
    assert eccesso == _SOGLIA.exceedance(20.0, 6.0)
    # Dimezzata dalla mappa del bias scende, ma resta lo stesso evento.
    corretto = _punteggio(serie, 600, 0.5)
    assert corretto[1] == 6.0 and corretto[0] is not None and corretto[0] < eccesso


def test_un_evento_finito_prima_della_finestra_non_conta() -> None:
    serie = _serie()
    serie[500:506] = 20.0  # finito 95 ore prima
    assert _punteggio(serie, 600) == (SENZA_EVENTO, None, None)


def test_una_finestra_non_misurata_non_e_una_finestra_asciutta() -> None:
    serie = _serie()
    serie[570:601] = np.nan
    assert _punteggio(serie, 600) == (None, None, None)
    assert _punteggio(_serie(), 100) == (None, None, None)  # manca la storia prima
    assert _punteggio(_serie(), 1000) == (None, None, None)  # oltre la fine


def test_il_radar_sulla_durata_del_pluviometro_cerca_la_fine_migliore() -> None:
    serie = _serie()
    serie[600:610] = 5.0  # l'evento vero finisce 9 ore dopo l'istante del catalogo
    assert sulla_stessa_durata(serie, 600, 10.0) == 50.0
    assert sulla_stessa_durata(serie, 600, 0.0) is None
    serie[580:640] = np.nan
    assert sulla_stessa_durata(serie, 600, 10.0) is None


def test_i_momenti_ordinari_stanno_lontani_dalle_frane() -> None:
    ore = 24 * 400
    liberi = istanti_ordinari(ore, [])
    assert liberi[0] == 15 * 24 + 48 and liberi[1] - liberi[0] == 30 * 24
    frana = liberi[3] + 24
    scelti = istanti_ordinari(ore, [frana])
    assert liberi[3] not in scelti and liberi[2] in scelti
    assert all(abs(e - frana) >= 15 * 24 for e in scelti)
    # Sfasati, due punti non guardano le stesse date.
    assert istanti_ordinari(ore, [], 37)[0] == liberi[0] + 37
    assert istanti_ordinari(ore, [], 720) == liberi


def test_una_data_senza_ora_di_italica_vale_fino_alla_fine_del_giorno(tmp_path: Path) -> None:
    testa = (
        "id;information_source;landslide_type;lon;lat;municipality;province;region;"
        "geographic_accuracy;land_cover;elevation;slope;day;month;year;local_time;local_date;"
        "utc_date;temporal_accuracy;lon_raingauge;lat_raingauge;duration;cumulated_rainfall"
    )
    righe = [
        "A;x;NA;8.9;44.4;c;p;Liguria;P0;NA;1;1;7;11;2019;;;07/11/2019 23:12;T1;8.9;44.4;18;95,4",
        "B;x;NA;13.1;43.5;c;p;Marche;P1;NA;1;1;17;1;2018;;;16/01/2018 23:00;T3;13;43;NA;NA",
        "C;x;NA;13.1;43.5;c;p;Marche;P1;NA;1;1;17;1;2017;;;16/01/2017 23:00;T3;13;43;NA;NA",
    ]
    csv = tmp_path / "italica.csv"
    csv.write_text("\n".join([testa, *righe]), encoding="utf-8")
    a, b = frane_italica(csv)
    assert (a.id, a.macro, a.pluvio_durata_h, a.pluvio_mm) == ("A", "northern", 18.0, 95.4)
    assert a.istante == datetime(2019, 11, 7, 23, 12, tzinfo=UTC)
    assert (b.id, b.macro, b.pluvio_mm) == ("B", "central", None)
    assert b.istante == datetime(2018, 1, 17, 23, 0, tzinfo=UTC)


def test_senza_abbastanza_unita_il_blocco_non_si_scrive() -> None:
    assert blocco("vuoto", [], []) == []
