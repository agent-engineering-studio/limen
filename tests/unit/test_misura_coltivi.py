"""Il report di ``limen misura-coltivi`` (#714): puro, dalle celle già lette."""

from __future__ import annotations

import argparse
from datetime import date

from limen.cli import misura_coltivi as mc

VERIFICA = (date(2024, 1, 1), date(2026, 12, 31))


def _cella(i: int, *, coltivo: float | None, bruciata: bool, giorni: int = 1) -> mc.Cella:
    return mc.Cella("it-x", 9.0 + 0.001 * i, 45.0, 100.0, giorni, coltivo, bruciata)


def _regione() -> mc.Regione:
    # Bruciano i boschi (quota bassa), non i campi: l'AUC esce sotto 0,5.
    celle = [_cella(i, coltivo=0.0, bruciata=i % 2 == 0) for i in range(10)]
    celle += [_cella(10 + i, coltivo=0.9, bruciata=i == 0, giorni=4) for i in range(10)]
    celle.append(_cella(99, coltivo=None, bruciata=False))  # niente terra: non misurato
    return mc.Regione("it-x", celle=1000, bruciate=12, con_fuoco=celle)


def test_report_says_who_the_share_can_see_and_its_direction() -> None:
    testo = mc.report([_regione()], stima_fino=date(2023, 12, 31), verifica=VERIFICA)
    assert "Celle 1000, bruciate 12" in testo
    assert "fra le bruciate 6 su 12 (50%)" in testo
    assert "più coltivo, **meno** incendi" in testo
    assert "| it-x | 21 | 6 |" in testo
    assert "2023-12-31" in testo and "2026-12-31" in testo


def test_a_region_without_burnt_cells_has_no_auc() -> None:
    vuota = mc.Regione(
        "it-y", celle=10, bruciate=0, con_fuoco=[_cella(1, coltivo=0.5, bruciata=False)]
    )
    testo = mc.report([_regione(), vuota], stima_fino=date(2023, 12, 31), verifica=VERIFICA)
    assert "| it-y | 1 | 0 | — |" in testo


async def test_verification_must_start_after_the_estimation() -> None:
    args = argparse.Namespace(
        regioni="it-x", stima_fino="2024-06-30", verifica="2024-2026", copertura=0.25
    )
    assert await mc.run(args) == 2
