"""Idrometri Arpae: lettura del mese, rapporti per stazione, campioni (#501)."""

from __future__ import annotations

import json
from datetime import date

from limen.cli.idrometri_misura import campioni, tabella
from limen.integrations.arpae.idrometri import leggi_mese, mesi, rapporti


def _riga(data: str, livello: float | None, *, lon: int = 1138497, rete: str = "cer") -> str:
    blocchi: list[dict[str, object]] = [
        {"vars": {"B01019": {"v": "S. Agostino Cavo"}, "B05001": {"v": 44.8}}}
    ]
    if livello is not None:
        blocchi.append({"timerange": [254, 0, 0], "level": [1], "vars": {"B13215": {"v": livello}}})
    # Un'altra variabile, cumulata: non è il livello e non va letta.
    blocchi.append({"timerange": [1, 0, 900], "vars": {"B13011": {"v": 3.0}}})
    return json.dumps({"network": rete, "lon": lon, "lat": 4479868, "date": data, "data": blocchi})


def test_mesi_attraversa_l_anno() -> None:
    assert mesi(date(2022, 11, 15), date(2023, 2, 1)) == [
        "2022-11",
        "2022-12",
        "2023-01",
        "2023-02",
    ]


def test_leggi_mese_tiene_il_massimo_giornaliero_per_stazione() -> None:
    livelli = leggi_mese(
        [
            _riga("2023-05-16T10:00:00Z", 7.1),
            _riga("2023-05-16T21:30:00Z", 9.7),
            _riga("2023-05-17T00:15:00Z", 9.2),
            _riga("2023-05-16T10:00:00Z", None),
            _riga("2023-05-16T10:00:00Z", 1.0, lon=1200000),
        ]
    )
    assert len(livelli.stazioni) == 2
    s = livelli.stazioni["cer:1138497:4479868"]
    assert (s.nome, round(s.lon, 5), round(s.lat, 5)) == ("S. Agostino Cavo", 11.38497, 44.79868)
    assert livelli.massimi["cer:1138497:4479868"] == {
        date(2023, 5, 16): 9.7,
        date(2023, 5, 17): 9.2,
    }


def test_rapporti_sulla_storia_della_stazione_prima_della_finestra() -> None:
    storia = {date(2022, 1, 1 + k): 1.0 + 0.01 * k for k in range(30)}
    giorni = {**storia, date(2023, 5, 16): 5.0}
    r = rapporti(giorni, prima_di=date(2023, 5, 1), percentile=0.9, minimo_giorni=20)
    assert list(r) == [date(2023, 5, 16)]
    # fondo p05 ≈ 1,0145, piena p90 ≈ 1,261: (5 - 1,0145) / 0,2465
    assert round(r[date(2023, 5, 16)], 1) == 16.2
    assert rapporti(giorni, prima_di=date(2023, 5, 1), percentile=0.9, minimo_giorni=60) == {}
    piatta = {date(2022, 1, 1 + k): 2.0 for k in range(30)}
    assert rapporti(piatta, prima_di=date(2023, 5, 1), percentile=0.9, minimo_giorni=20) == {}


def test_campioni_piena_qualunque_e_giorno_prima() -> None:
    serie = {date(2023, 5, d): float(d) for d in range(1, 31)}
    piene = {"s": {date(2023, 5, 16), date(2023, 5, 17)}}
    stesso = campioni({"s": serie}, piene, ritardo=0)
    assert stesso.piena == [16.0, 17.0]
    # Lontano più di tre giorni da ogni piena: 1-12 e 21-30.
    assert len(stesso.qualunque) == 22
    prima = campioni({"s": serie}, piene, ritardo=1)
    assert prima.piena == [15.0, 16.0]
    righe = tabella("prova", stesso)
    assert righe[0] == "### prova"
    assert any(r.startswith("| giorni di piena | 2 |") for r in righe)
