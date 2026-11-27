"""Acqua osservata EMS contro le classi idrauliche (#713): l'aritmetica, senza DB."""

from __future__ import annotations

import pytest
from shapely.geometry import box

from limen.core.ems_pai import Ripartizione, di_monitoraggio, prodotto, ripartisci


def test_prodotto_toglie_posizione_e_parte() -> None:
    assert prodotto("EMSR664-aoi01-DEL1-29-0") == "EMSR664-aoi01-DEL1"


@pytest.mark.parametrize(
    ("codice", "atteso"),
    [
        ("EMSR664-aoi01-DEL0", False),
        ("EMSR664-aoi02-GRA0", False),
        ("EMSR659-aoi01-FEP0", False),
        ("EMSR664-aoi01-DEL1", True),
        ("EMSR705-aoi01-DEL2", True),
        ("illeggibile", True),
    ],
)
def test_monitoraggio(codice: str, atteso: bool) -> None:
    assert di_monitoraggio(codice) is atteso


def test_classi_esclusive_vince_la_piu_alta() -> None:
    # Acqua 100 x 100 m. P1 la copre tutta, P2 la metà sinistra, P3 un quarto:
    # nidificate come nel mosaico ISPRA.
    acqua = [box(0, 0, 100, 100)]
    zone = [
        ("P1", box(-10, -10, 110, 110)),
        ("P2", box(-10, -10, 50, 110)),
        ("P3", box(-10, -10, 25, 110)),
    ]
    r = ripartisci(acqua, zone, tolleranza_m=0.0, patch_minima_m2=0.0)
    assert r.acqua_m2 == pytest.approx(10_000)
    assert r.per_classe_m2["P3"] == pytest.approx(2_500)
    assert r.per_classe_m2["P2"] == pytest.approx(2_500)
    assert r.per_classe_m2["P1"] == pytest.approx(5_000)
    assert r.fuori_m2 == pytest.approx(0.0, abs=1e-6)
    assert sum(r.per_classe_m2.values()) + r.fuori_m2 == pytest.approx(r.acqua_m2)


def test_unione_non_somma() -> None:
    # Due prodotti che ridisegnano lo stesso campo contano una volta.
    acqua = [box(0, 0, 100, 100), box(0, 0, 100, 100), box(50, 0, 150, 100)]
    r = ripartisci(acqua, [], tolleranza_m=0.0, patch_minima_m2=0.0)
    assert r.acqua_m2 == pytest.approx(15_000)
    assert r.fuori_m2 == pytest.approx(15_000)


def test_striscia_sul_bordo_esce_dal_filtrato() -> None:
    # Una zona P3 0..1000; l'acqua sborda di 20 m (striscia) e c'è una macchia
    # lontana di 300 x 300 m (9 ha) e una piccola di 100 x 100 m (1 ha).
    zone = [("P3", box(0, 0, 1000, 1000))]
    acqua = [
        box(0, 0, 1020, 1000),
        box(2000, 0, 2300, 300),
        box(3000, 0, 3100, 100),
    ]
    r = ripartisci(acqua, zone, tolleranza_m=50.0, patch_minima_m2=50_000.0)
    assert r.fuori_m2 == pytest.approx(20 * 1000 + 90_000 + 10_000)
    assert r.fuori_filtrato_m2 == pytest.approx(90_000)
    assert r.macchie_fuori == 1


def test_tolleranza_e_patch_si_regolano() -> None:
    zone = [("P2", box(0, 0, 1000, 1000))]
    acqua = [box(0, 0, 1100, 1000)]
    stretto = ripartisci(acqua, zone, tolleranza_m=50.0, patch_minima_m2=10_000.0)
    largo = ripartisci(acqua, zone, tolleranza_m=150.0, patch_minima_m2=10_000.0)
    assert stretto.fuori_filtrato_m2 == pytest.approx(50 * 1000)
    assert largo.fuori_filtrato_m2 == 0.0


def test_macchia_tagliata_dalle_tessere_resta_una() -> None:
    # 3 km di lato: tagliata in quattro tessere da 2 km, deve tornare una macchia.
    r = ripartisci([box(1000, 1000, 4000, 4000)], [], tolleranza_m=50.0, patch_minima_m2=50_000.0)
    assert r.macchie_fuori == 1
    assert r.fuori_filtrato_m2 == pytest.approx(9_000_000)


def test_senza_acqua() -> None:
    r = ripartisci([], [("P3", box(0, 0, 1, 1))])
    assert r.acqua_m2 == 0.0
    assert r.quota(r.fuori_m2) is None


def test_quota() -> None:
    r = Ripartizione(200.0, {"P3": 50.0, "P2": 0.0, "P1": 0.0}, 150.0, 0.0, 0)
    assert r.quota(r.per_classe_m2["P3"]) == pytest.approx(0.25)
