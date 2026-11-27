"""Il riepilogo sulla qualità dei dati, dai fatti alle parole (#421)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from limen.core.qualita_dati import Cadenza, Errore, Fatti, pulisci, righe
from limen.core.qualita_dati import testo as riepilogo

ORA = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)


def _fatti(
    *,
    errori: Sequence[Errore] = (),
    cadenze: Sequence[Cadenza] = (),
    non_misurate: Mapping[str, tuple[int, int]] | None = None,
) -> Fatti:
    return Fatti(ORA, errori, cadenze, non_misurate or {})


def test_un_job_orario_fermo_da_tre_ore_e_in_ritardo() -> None:
    fermo = Cadenza(
        "limen-hourly-monitoring", None, ORA - timedelta(hours=3), timedelta(hours=1), 600
    )
    puntuale = Cadenza("limen-nightly", "backup", ORA - timedelta(hours=20), timedelta(days=1), 29)
    f = _fatti(cadenze=[fermo, puntuale])
    assert [r.job_id for r in f.ritardi()] == ["limen-hourly-monitoring"]
    assert righe(f, None) == [
        "**limen-hourly-monitoring** è fermo: ultimo successo 3 h fa, di solito gira ogni 1 h."
    ]


def test_senza_storia_non_si_giudica() -> None:
    nuovo = Cadenza("limen-nuovo", None, ORA - timedelta(days=5), timedelta(hours=1), 2)
    assert _fatti(cadenze=[nuovo]).ritardi() == []


def test_un_errore_porta_il_messaggio_e_l_ora() -> None:
    e = Errore("limen-nightly", "backup", 2, ORA - timedelta(hours=1), "disco pieno")
    assert righe(_fatti(errori=[e]), None) == [
        "**limen-nightly (backup)** è fallito 2 volte nelle ultime 24 ore, "
        "l'ultima alle 02:00 UTC: «disco pieno»."
    ]


def test_i_segreti_di_un_url_non_escono() -> None:
    m = "HTTP 403 for https://firms.modaps.eosdis.nasa.gov/api/area/csv?MAP_KEY=abc123&x=1 token=zz"
    assert pulisci(m) == (
        "HTTP 403 for https://firms.modaps.eosdis.nasa.gov/api/area/csv?MAP_KEY=<nascosto>&x=1 "
        "token=<nascosto>"
    )


def test_non_misurate_sopra_la_meta_o_in_salita() -> None:
    f = _fatti(
        non_misurate={"flood": (6000, 10000), "wildfire": (900, 10000), "landslide": (0, 10)}
    )
    # Alluvione sopra la metà; incendio al 9 % ma salito dal 2 %: entrambi.
    prima = {"non_misurate": {"flood": 0.58, "wildfire": 0.02}}
    assert righe(f, prima) == [
        "Pericolo **flood**: 60,0 % delle celle non misurate (una settimana fa 58,0 %): "
        "manca il dato meteo, non è quiete.",
        "Pericolo **wildfire**: 9,0 % delle celle non misurate (una settimana fa 2,0 %): "
        "manca il dato meteo, non è quiete.",
    ]
    # Senza la settimana prima il 9 % non si segnala.
    assert len(righe(f, None)) == 1


def test_niente_da_segnalare_e_lo_dice() -> None:
    t = riepilogo(_fatti(), None)
    assert t.startswith("# Qualità dei dati — 2026-11-11 03:00 UTC")
    assert "Niente da segnalare" in t


def test_metriche_per_la_settimana_dopo() -> None:
    f = _fatti(
        errori=[Errore("a", None, 3, ORA, None), Errore("a", "x", 1, ORA, None)],
        non_misurate={"flood": (1, 4)},
    )
    assert f.metriche() == {
        "errori": 4,
        "job_con_errori": 1,
        "in_ritardo": [],
        "non_misurate": {"flood": 0.25},
        "tabelle_mancanti": {},
        "ispra_cambiati": 0,
    }


def test_un_guasto_su_tutte_le_regioni_e_una_riga() -> None:
    regioni = [f"it-r{i:02d}" for i in range(20)]
    fermi = [
        Cadenza("limen-hourly-monitoring", r, ORA - timedelta(hours=15), timedelta(hours=1), 600)
        for r in regioni
    ]
    errori = [
        Errore("limen-hourly-monitoring", r, 42, ORA - timedelta(minutes=5), "colonna mancante")
        for r in regioni
    ] + [Errore("limen-hourly-monitoring", None, 1, ORA - timedelta(hours=3), "TimeoutError: ")]
    out = righe(_fatti(errori=errori, cadenze=fermi), None)
    assert out == [
        "**limen-hourly-monitoring** è fermo in 20 ambiti (it-r00, it-r01, it-r02, it-r03, "
        "it-r04 e altri 15): ultimo successo 15 h fa, di solito gira ogni 1 h.",
        "**limen-hourly-monitoring** è fallito in 20 ambiti (it-r00, it-r01, it-r02, it-r03, "
        "it-r04 e altri 15) 840 volte nelle ultime 24 ore, l'ultima alle 02:55 UTC: "
        "«colonna mancante».",
        "**limen-hourly-monitoring** è fallito una volta nelle ultime 24 ore, "
        "l'ultima alle 00:00 UTC: «TimeoutError: ».",
    ]


def test_un_job_con_la_riga_nazionale_si_giudica_su_quella() -> None:
    nazionale = Cadenza(
        "limen-nowcast-monitoring", None, ORA - timedelta(minutes=10), timedelta(minutes=15), 900
    )
    regione = Cadenza(
        "limen-nowcast-monitoring", "it-lombardia", ORA - timedelta(days=4), timedelta(hours=1), 40
    )
    assert _fatti(cadenze=[nazionale, regione]).ritardi() == []
    fermo = Cadenza(
        "limen-nowcast-monitoring", None, ORA - timedelta(hours=2), timedelta(minutes=15), 900
    )
    assert [r.scope for r in _fatti(cadenze=[fermo, regione]).ritardi()] == [None]


def test_una_tabella_iffi_mancante_si_dice_per_regione() -> None:
    """#665: una regione senza la tabella non è una regione senza frane."""
    f = Fatti(
        ORA,
        [],
        [],
        {},
        tabelle_mancanti={
            "it-molise": ["frane_poly_molise_opendata"],
            "it-puglia": ["a", "b", "c", "d"],
        },
    )
    out = righe(f, None)
    assert out == [
        "**it-molise**: una tabella attesa non trovata all'ultimo geoserver-sync "
        "(frane_poly_molise_opendata): le celle perdono quel termine, "
        "non sono senza frane o senza pericolo.",
        "**it-puglia**: 4 tabelle attese non trovate all'ultimo geoserver-sync "
        "(a, b, c e altre 1): le celle perdono quel termine, "
        "non sono senza frane o senza pericolo.",
    ]
    assert f.metriche()["tabelle_mancanti"] == {"it-molise": 1, "it-puglia": 4}


def test_file_ispra_cambiati_in_una_riga() -> None:
    f = Fatti(
        ORA,
        (),
        (),
        {},
        ispra_cambiati=[
            "Mosaicatura_ISPRA_2024_pericolosita_frana_PAI.zip",
            "frane_piff_puglia_opendata.zip",
            "frane_poly_puglia_opendata.zip",
        ],
    )
    assert righe(f, None) == [
        "**IdroGEO**: 2 file IFFI e il mosaico Mosaicatura_ISPRA_2024_pericolosita_frana_PAI "
        "sono cambiati rispetto alla copia caricata: `make static-data` li riscarica e li ricarica."
    ]
    assert f.metriche()["ispra_cambiati"] == 3


def test_idrogeo_muto_non_e_niente_di_cambiato() -> None:
    f = Fatti(ORA, (), (), {}, ispra_cambiati=None)
    assert righe(f, None) == [
        "**IdroGEO** non ha risposto: non si sa se i file ISPRA sono cambiati."
    ]
    assert f.metriche()["ispra_cambiati"] is None


def test_nessun_file_ispra_cambiato_nessuna_riga() -> None:
    assert righe(_fatti(), None) == []
