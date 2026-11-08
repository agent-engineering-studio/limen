"""Una regione caricata ma tutta a zero è «da verificare» (#467).

Il caso vero è IFFI in Trentino-Alto Adige (#454): il file andava letto dalle
due Province, la densità è finita a zero su ogni cella e il conteggio dei
valori la dava «caricata», perché zero è un valore. Le quote qui sotto sono
quelle misurate il 2026-11-08 (celle con ``iffi_density_500 > 0``), con il
Trentino riportato a zero.
"""

from __future__ import annotations

from limen.config.catalogo_dati import carica_catalogo
from limen.core.installazione import regioni_da_verificare

_CELLE = {
    "it-trentino-alto-adige": 14078,
    "it-puglia": 20075,
    "it-sardegna": 25008,
    "it-veneto": 18971,
    "it-toscana": 23779,
    "it-marche": 9697,
    "it-basilicata": 10353,
}
_QUOTA_IFFI = {
    "it-trentino-alto-adige": 0.0,
    "it-puglia": 0.068,
    "it-sardegna": 0.137,
    "it-veneto": 0.280,
    "it-toscana": 0.877,
    "it-marche": 0.964,
    "it-basilicata": 0.732,
}


def _sospette(quote: dict[str, float]) -> list[str]:
    per_regione = {aoi: {"iffi": n} for aoi, n in _CELLE.items()}
    informativi = {aoi: {"iffi": round(q * _CELLE[aoi])} for aoi, q in quote.items()}
    return regioni_da_verificare(carica_catalogo(), per_regione, informativi, _CELLE)["iffi"]


def test_il_trentino_a_zero_e_da_verificare_e_la_puglia_no() -> None:
    # La Puglia ha davvero poche frane censite (6,8 %): bassa, non sbagliata.
    assert _sospette(_QUOTA_IFFI) == ["it-trentino-alto-adige"]


def test_caricato_bene_ovunque_non_segnala_niente() -> None:
    assert _sospette({**_QUOTA_IFFI, "it-trentino-alto-adige": 0.853}) == []


def test_tutto_a_zero_segnala_tutte_le_regioni() -> None:
    # Mediana zero: il confronto con le altre regioni non regge più.
    assert _sospette(dict.fromkeys(_QUOTA_IFFI, 0.0)) == sorted(_CELLE)


def test_una_regione_senza_il_dato_non_e_da_verificare_ma_mancante() -> None:
    per_regione = {aoi: {"iffi": n} for aoi, n in _CELLE.items()}
    per_regione["it-trentino-alto-adige"] = {"iffi": 0}
    informativi = {aoi: {"iffi": round(q * _CELLE[aoi])} for aoi, q in _QUOTA_IFFI.items()}
    sospette = regioni_da_verificare(carica_catalogo(), per_regione, informativi, _CELLE)
    assert "it-trentino-alto-adige" not in sospette["iffi"]


def test_solo_le_voci_dichiarate_informative_si_controllano() -> None:
    catalogo = carica_catalogo()
    informative = {v.id for v in catalogo.voci if v.misura.informativo == "positivi"}
    assert informative == {"iffi", "pai_frana", "idraulica", "impermeabilizzazione", "wui"}
    assert set(regioni_da_verificare(catalogo, {}, {}, {})) == informative
