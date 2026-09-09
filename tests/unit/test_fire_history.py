"""Archivio storico FIRMS: classificazione e URL (#66).

Due cose che il codice può sbagliare in silenzio, entrambe provate qui perché
non richiedono rete:

1. **La classe della detection.** FIRMS pubblica una colonna `type` che dice
   *cosa* ha visto il satellite. Ignorarla ha prodotto una densità del fuoco
   la cui cella massima d'Italia era l'ILVA di Taranto, con 3.308
   giorni-incendio su ~4.700 giorni d'archivio. Il filtro di confidenza non
   la toglieva e non poteva: un'acciaieria è calda davvero.
2. **Il riconoscimento di un corpo che non è un CSV.** Gli anni non
   pubblicati non rispondono sempre 404, e un messaggio d'errore dato in
   pasto al parser produce zero righe senza spiegare perché.
"""

from __future__ import annotations

from limen.integrations.firms.archive import (
    ARCHIVE_PRODUCTS,
    ARCHIVE_URL,
    _looks_like_hotspot_csv,
    archive_years,
)
from limen.integrations.firms.client import parse_hotspot_csv

_VIIRS_HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight,type"
)


def _viirs_row(*, lat: float, lon: float, detection_type: int, confidence: str = "h") -> str:
    return (
        f"{lat},{lon},330.1,0.5,0.5,2024-08-01,1130,N,VIIRS,"
        f"{confidence},2,290.0,12.5,D,{detection_type}"
    )


def test_detection_type_is_parsed_from_the_archive_csv() -> None:
    payload = "\n".join(
        [
            _VIIRS_HEADER,
            _viirs_row(lat=40.5, lon=16.1, detection_type=0),
            _viirs_row(lat=40.508, lon=17.210, detection_type=2),
            _viirs_row(lat=37.75, lon=14.99, detection_type=1),
            _viirs_row(lat=40.0, lon=18.5, detection_type=3),
        ]
    )

    hotspots = parse_hotspot_csv(payload, source="VIIRS_SNPP_SP")

    assert [h.detection_type for h in hotspots] == [0, 2, 1, 3]


def test_a_steelworks_is_high_confidence_so_only_the_class_separates_it() -> None:
    """Il motivo per cui il filtro di qualità non bastava.

    La detection di Taranto ha confidenza alta e potenza radiativa alta: passa
    ogni soglia di qualità, perché è una misura corretta di un oggetto molto
    caldo. Solo `type` dice che non è un incendio.
    """
    payload = "\n".join(
        [
            _VIIRS_HEADER,
            _viirs_row(lat=40.508, lon=17.210, detection_type=2, confidence="h"),
        ]
    )

    hotspots = parse_hotspot_csv(
        payload, source="VIIRS_SNPP_SP", min_confidence="high", min_frp_mw=10.0
    )

    assert len(hotspots) == 1, "il filtro di qualità la tiene, ed è corretto"
    assert hotspots[0].detection_type == 2, "la classe è l'unica cosa che la esclude"


def test_missing_type_column_leaves_the_class_unknown() -> None:
    """Un feed che non porta la colonna non deve far inventare uno zero.

    `fire_events` conta solo il tipo 0, quindi `None` tiene la detection fuori
    dagli eventi: sbagliare per difetto perde qualche giorno, sbagliare per
    eccesso rimette un'acciaieria nel truth set ogni giorno.
    """
    header = _VIIRS_HEADER.replace(",type", "")
    row = _viirs_row(lat=40.5, lon=16.1, detection_type=0).rsplit(",", 1)[0]

    hotspots = parse_hotspot_csv("\n".join([header, row]), source="VIIRS_SNPP_SP")

    assert len(hotspots) == 1
    assert hotspots[0].detection_type is None


def test_an_error_body_is_not_mistaken_for_a_csv() -> None:
    assert _looks_like_hotspot_csv(_VIIRS_HEADER)
    assert not _looks_like_hotspot_csv('{"error":"not found"}')
    assert not _looks_like_hotspot_csv("")
    # Un HTML di errore contiene parole comuni ma non le colonne richieste.
    assert not _looks_like_hotspot_csv("<html><body>Not Found</body></html>")


def test_archive_url_matches_the_published_layout() -> None:
    url = ARCHIVE_URL.format(source="viirs-snpp", year=2020, country="Italy")
    assert url == (
        "https://firms.modaps.eosdis.nasa.gov/data/country/"
        "viirs-snpp/2020/viirs-snpp_2020_Italy.csv"
    )


def test_each_product_starts_at_its_own_first_published_year() -> None:
    """MODIS dal 2000, VIIRS dal 2012: chiedere a VIIRS il 2005 è una
    richiesta sprecata verso una risposta che non è un CSV."""
    by_slug = {p.slug: p for p in ARCHIVE_PRODUCTS}

    assert by_slug["modis"].first_year == 2000
    assert by_slug["viirs-snpp"].first_year == 2012
    assert archive_years(by_slug["viirs-snpp"], until_year=2014) == [2012, 2013, 2014]
    assert archive_years(by_slug["modis"], until_year=2001) == [2000, 2001]


def test_sources_are_distinct_from_the_nrt_products() -> None:
    """L'archivio è standard processing, l'NRT è un altro prodotto.

    La chiave naturale di `fire_hotspots` contiene `source`: schiacciarli sullo
    stesso valore renderebbe impossibile sapere da dove viene una detection, e
    un riprocessamento sovrascriverebbe una riga NRT con una d'archivio.
    """
    sources = {p.source for p in ARCHIVE_PRODUCTS}

    assert sources == {"MODIS_SP", "VIIRS_SNPP_SP"}
    assert not any(s.endswith("_NRT") for s in sources)
