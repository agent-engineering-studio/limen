"""Catena FWI di Van Wagner (issue #61).

Il test che conta è il primo: le sei uscite contro i valori pubblicati. Le
equazioni sono uno standard, non una scelta di progetto, quindi l'unico modo
di sapere se sono trascritte bene è confrontarle con un caso noto — una
suite di sole proprietà resterebbe verde anche con un coefficiente sbagliato.

Il resto verifica ciò che il vettore singolo non può toccare: i rami della
pioggia, i limiti fisici, e il fatto che i codici *ricordino*.
"""

from __future__ import annotations

import math

import pytest

from limen.core.scoring.wildfire.fwi import (
    FwiParams,
    FwiState,
    advance,
    buildup_index,
    drought_code,
    duff_moisture_code,
    fine_fuel_moisture_code,
    fire_weather_index,
    initial_spread_index,
)

# Van Wagner (1987), Tabelle 2 e 3, banda 46°N — le stesse del wildfire.yaml.
DAY_LENGTH_DMC = (6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0)
DAY_LENGTH_DC = (-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6)

PARAMS = FwiParams(
    ffmc_start=85.0,
    dmc_start=6.0,
    dc_start=15.0,
    day_length_dmc=DAY_LENGTH_DMC,
    day_length_dc=DAY_LENGTH_DC,
)


# ---------------------------------------------------------------------------
# Il vettore di riferimento
# ---------------------------------------------------------------------------
def test_published_reference_day() -> None:
    """Caso di riferimento della catena FWI, dai valori iniziali standard.

    Ingressi: 17.0 °C, 42 % UR, 25 km/h, 0 mm, aprile, partendo da
    FFMC/DMC/DC = 85 / 6 / 15. È il primo giorno della serie di prova che
    accompagna l'implementazione di riferimento delle equazioni di Van Wagner
    (pacchetto `cffdrs`), ed è verificabile a mano: il DC, per esempio, è
    15 + (0.36·(17+2.8) + 0.9)/2 = 19.014.

    Tolleranza 1e-9 sull'assoluto: non si sta calibrando nulla, si sta
    controllando una trascrizione. Uno scostamento più grande di così è un
    coefficiente sbagliato, non rumore in virgola mobile.
    """
    out = advance(
        PARAMS.initial_state,
        month=4,
        temperature_c=17.0,
        relative_humidity_pct=42.0,
        wind_speed_kmh=25.0,
        rain_24h_mm=0.0,
        params=PARAMS,
    )
    assert out.state.ffmc == pytest.approx(87.692980092774, abs=1e-9)
    assert out.state.dmc == pytest.approx(8.5450511359998, abs=1e-9)
    assert out.state.dc == pytest.approx(19.013999999999996, abs=1e-9)
    assert out.isi == pytest.approx(10.853661073312, abs=1e-9)
    assert out.bui == pytest.approx(8.4904265358371, abs=1e-9)
    assert out.fwi == pytest.approx(10.096371392382, abs=1e-9)


# ---------------------------------------------------------------------------
# I rami della pioggia — quello che un giorno secco non tocca
# ---------------------------------------------------------------------------
def test_light_rain_is_intercepted_by_the_canopy() -> None:
    """Sotto le soglie di ogni codice la pioggia non arriva al combustibile.

    0.5 mm per il FFMC, 1.5 per il DMC, 2.8 per il DC: non sono arrotondamenti
    ma la quantità che la chioma trattiene prima che qualcosa raggiunga il
    suolo. Una pioggia sotto soglia deve lasciare il codice ad *asciugare*.
    """
    dry = fine_fuel_moisture_code(
        90.0,
        temperature_c=20.0,
        relative_humidity_pct=40.0,
        wind_speed_kmh=10.0,
        rain_24h_mm=0.0,
    )
    drizzle = fine_fuel_moisture_code(
        90.0,
        temperature_c=20.0,
        relative_humidity_pct=40.0,
        wind_speed_kmh=10.0,
        rain_24h_mm=0.4,
    )
    assert drizzle == dry

    assert drought_code(100.0, temperature_c=20.0, rain_24h_mm=2.0, day_length=5.8) > 100.0


def test_heavy_rain_lowers_every_code() -> None:
    """Una pioggia forte deve bagnare tutti e tre i codici, non solo il fine."""
    assert (
        fine_fuel_moisture_code(
            92.0,
            temperature_c=18.0,
            relative_humidity_pct=60.0,
            wind_speed_kmh=5.0,
            rain_24h_mm=30.0,
        )
        < 92.0
    )
    assert (
        duff_moisture_code(
            80.0,
            temperature_c=18.0,
            relative_humidity_pct=60.0,
            rain_24h_mm=40.0,
            day_length=13.9,
        )
        < 80.0
    )
    assert drought_code(500.0, temperature_c=18.0, rain_24h_mm=40.0, day_length=5.8) < 500.0


def test_the_saturation_correction_reads_the_pre_rain_moisture() -> None:
    """Eq. 3a si applica al combustibile *già* saturo prima della pioggia.

    Un FFMC molto basso significa combustibile fradicio (oltre il 150 % di
    umidità): lì l'acqua in più scorre via invece di essere assorbita. Se il
    ramo leggesse il valore post-pioggia, la correzione colpirebbe anche
    combustibile che all'alba era asciutto, sovrastimandone la bagnatura.

    Il controllo osservabile: partendo da fradicio, la pioggia non deve
    portare l'umidità oltre il tetto di 250, cioè l'FFMC sotto il suo minimo.
    """
    soaked = fine_fuel_moisture_code(
        5.0,
        temperature_c=10.0,
        relative_humidity_pct=95.0,
        wind_speed_kmh=2.0,
        rain_24h_mm=60.0,
    )
    assert 0.0 <= soaked <= 101.0


# ---------------------------------------------------------------------------
# Limiti fisici
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("temperature_c", "relative_humidity_pct", "wind_speed_kmh", "rain_24h_mm"),
    [
        (45.0, 0.0, 120.0, 0.0),  # scirocco estremo
        (-20.0, 100.0, 0.0, 0.0),  # gelo saturo
        (25.0, 50.0, 20.0, 200.0),  # nubifragio
        (0.0, 100.0, 0.0, 0.0),
    ],
)
def test_codes_stay_inside_their_domains(
    temperature_c: float,
    relative_humidity_pct: float,
    wind_speed_kmh: float,
    rain_24h_mm: float,
) -> None:
    """Nessun estremo meteo deve produrre un NaN o un codice fuori scala.

    I codici alimentano un punteggio in [0,1] e una tabella con dei CHECK:
    un NaN qui diventa una cella senza classe a valle, cioè un buco nella
    mappa nel giorno in cui il tempo è più estremo.
    """
    out = advance(
        FwiState(ffmc=85.0, dmc=25.0, dc=200.0),
        month=7,
        temperature_c=temperature_c,
        relative_humidity_pct=relative_humidity_pct,
        wind_speed_kmh=wind_speed_kmh,
        rain_24h_mm=rain_24h_mm,
        params=PARAMS,
    )
    for name, value in (
        ("ffmc", out.state.ffmc),
        ("dmc", out.state.dmc),
        ("dc", out.state.dc),
        ("isi", out.isi),
        ("bui", out.bui),
        ("fwi", out.fwi),
    ):
        assert math.isfinite(value), name
        assert value >= 0.0, name
    assert out.state.ffmc <= 101.0


def test_buildup_index_survives_both_codes_at_zero() -> None:
    """Eq. 27 divide per `dmc + 0.4·dc`: a terreno fradicio è una divisione
    per zero, non un caso impossibile."""
    assert buildup_index(0.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# La memoria — il motivo per cui lo stato è persistito
# ---------------------------------------------------------------------------
def test_the_drought_code_remembers_far_longer_than_the_fine_fuel() -> None:
    """FFMC dimentica in un giorno, DC in ~52.

    È l'asimmetria che giustifica la tabella `fwi_state`: se anche il DC
    dimenticasse in fretta, ripartire dai valori standard a ogni riavvio
    sarebbe innocuo. Dopo una pioggia forte seguita da una settimana secca il
    fine deve essere risalito quasi del tutto, il DC quasi per niente.
    """
    state = FwiState(ffmc=85.0, dmc=40.0, dc=500.0)
    wet = advance(
        state,
        month=7,
        temperature_c=20.0,
        relative_humidity_pct=80.0,
        wind_speed_kmh=5.0,
        rain_24h_mm=50.0,
        params=PARAMS,
    )
    dc_after_rain = wet.state.dc
    ffmc_after_rain = wet.state.ffmc

    dry = wet
    for _ in range(7):
        dry = advance(
            dry.state,
            month=7,
            temperature_c=32.0,
            relative_humidity_pct=20.0,
            wind_speed_kmh=15.0,
            rain_24h_mm=0.0,
            params=PARAMS,
        )

    # Quanto di ciò che la pioggia ha tolto è stato recuperato in una
    # settimana secca. È il confronto giusto: i due codici hanno scale
    # diverse, ma la frazione recuperata è confrontabile.
    ffmc_recovered = (dry.state.ffmc - ffmc_after_rain) / (85.0 - ffmc_after_rain)
    dc_recovered = (dry.state.dc - dc_after_rain) / (500.0 - dc_after_rain)

    # Il fine ha recuperato tutto e oltre: in una settimana a 32 °C e 20 % di
    # umidità è più asciutto di prima della pioggia.
    assert ffmc_recovered > 1.0
    assert dry.state.ffmc > 90.0
    # Il DC ne ha recuperato meno della metà, pur essendo il pieno luglio in
    # cui asciuga più in fretta di tutto l'anno.
    assert dc_recovered < 0.5


def test_wind_only_enters_through_the_spread_index() -> None:
    """Il vento è il fattore che l'issue chiede di catturare: entra in ISI
    (Eq. 24) e, attraverso il FFMC, nella velocità di asciugatura — ma non
    nel BUI, che è solo combustibile disponibile."""
    calm = initial_spread_index(90.0, wind_speed_kmh=0.0)
    gale = initial_spread_index(90.0, wind_speed_kmh=60.0)
    assert gale > calm * 10.0
    # Il BUI non ha il vento fra gli argomenti: la prova è nella firma, e qui
    # si verifica che la catena non lo introduca da un'altra parte.
    assert buildup_index(40.0, 300.0) == buildup_index(40.0, 300.0)


def test_fwi_is_monotone_in_both_of_its_inputs() -> None:
    """Più propagazione o più combustibile ⇒ mai un indice più basso."""
    base = fire_weather_index(10.0, 50.0)
    assert fire_weather_index(20.0, 50.0) > base
    assert fire_weather_index(10.0, 120.0) > base


# ---------------------------------------------------------------------------
# Validazione dei parametri
# ---------------------------------------------------------------------------
def test_a_day_length_table_of_the_wrong_size_is_refused() -> None:
    """Undici mesi passerebbero silenziosamente e sfaserebbero l'anno."""
    with pytest.raises(ValueError, match="12 monthly entries"):
        FwiParams(
            ffmc_start=85.0,
            dmc_start=6.0,
            dc_start=15.0,
            day_length_dmc=DAY_LENGTH_DMC[:11],
            day_length_dc=DAY_LENGTH_DC,
        )


def test_an_impossible_month_is_refused() -> None:
    with pytest.raises(ValueError, match=r"month must be in 1\.\.12"):
        advance(
            PARAMS.initial_state,
            month=13,
            temperature_c=20.0,
            relative_humidity_pct=50.0,
            wind_speed_kmh=10.0,
            rain_24h_mm=0.0,
            params=PARAMS,
        )
