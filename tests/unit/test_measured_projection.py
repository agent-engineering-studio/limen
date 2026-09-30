"""«Non misurato» è una risposta, «zero» è un'altra (#143).

Un'integrazione degradata restituisce un risultato neutro, e per un motore
moltiplicativo il risultato neutro è **zero**. Il 29 settembre 2026 il tetto
giornaliero di Open-Meteo è saltato e ogni cella d'Italia si è ritrovata con
alluvione e incendio a 0,0000: sulla mappa, in fondo alla scala, accanto alla
scritta della classe più tranquilla.

Non è ricavabile dal punteggio — una cella genuinamente calma vale zero anche
lei. La differenza la conosce solo il breakdown, ed è lui a rispondere.
"""

from __future__ import annotations

from datetime import date

from limen.core.models.risk import (
    ComponentBreakdown,
    FireWeatherState,
    FloodBreakdown,
    MeteoBreakdown,
    StaticBreakdown,
    WildfireBreakdown,
)


def _incendio(fw: FireWeatherState | None) -> WildfireBreakdown:
    return WildfireBreakdown(fwi_norm=0.0, fuel=0.3, slope=0.8, fire_weather=fw, spinup=True)


def _catena() -> FireWeatherState:
    return FireWeatherState(
        day=date(2026, 9, 29),
        ffmc=89.8,
        dmc=31.2,
        dc=77.0,
        isi=6.9,
        bui=31.2,
        fwi=13.3,
        chain_days=15,
    )


def test_incendio_senza_catena_non_e_misurato() -> None:
    assert _incendio(None).measured() is False


def test_incendio_con_catena_e_misurato_anche_in_rodaggio() -> None:
    # `spinup` non basta a distinguerli: è vero anche per una catena corta
    # ma reale, che un punteggio ce l'ha.
    breakdown = _incendio(_catena())
    assert breakdown.spinup is True
    assert breakdown.measured() is True


def test_alluvione_senza_nessuno_dei_due_segnali_non_e_misurata() -> None:
    secca = FloodBreakdown(
        susceptibility=0.4, pluvial=0.0, fluvial=0.0, rain_mm=None, discharge_ratio=None
    )
    assert secca.measured() is False


def test_alluvione_con_un_solo_segnale_e_misurata() -> None:
    # «Piove ma non so quanto è grosso il fiume» è un'alluvione misurata a
    # metà, non una non misurata.
    solo_pioggia = FloodBreakdown(
        susceptibility=0.4, pluvial=0.2, fluvial=0.0, rain_mm=12.0, discharge_ratio=None
    )
    solo_fiume = FloodBreakdown(
        susceptibility=0.4, pluvial=0.0, fluvial=0.3, rain_mm=None, discharge_ratio=1.4
    )
    assert solo_pioggia.measured() is True
    assert solo_fiume.measured() is True


def test_zero_misurato_resta_misurato() -> None:
    # Una giornata asciutta: i segnali sono arrivati e dicono «niente». È la
    # cella calma, ed è giusto che si colori come tale.
    asciutta = FloodBreakdown(
        susceptibility=0.4, pluvial=0.0, fluvial=0.0, rain_mm=0.0, discharge_ratio=0.1
    )
    assert asciutta.measured() is True


def test_la_frana_sta_in_piedi_sul_terreno() -> None:
    # S/M/E non sono tutti meteo: senza pioggia il punteggio poggia ancora
    # sulla suscettibilità del versante, quindi significa qualcosa.
    frana = ComponentBreakdown(
        s=0.8,
        m=0.0,
        e=0.1,
        f=0.0,
        h=0.0,
        static_terms=StaticBreakdown(
            susc_ispra=0.8, iffi_density=0.2, slope=0.6, pai=0.5, litho_weight=0.5
        ),
        # Il meteo mancante: il fattore suolo al punto medio, che è come
        # il motore tratta un'umidità che non conosce.
        meteo_terms=MeteoBreakdown(
            caine_excess=0.0, caine_norm=0.0, api_factor=0.0, soil_factor=0.5
        ),
    )
    assert frana.measured() is True
